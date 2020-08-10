import configparser
import logging
from notion.client import NotionClient
from notion.block import HeaderBlock, SubheaderBlock, SubsubheaderBlock, TextBlock, PageBlock

appname = "Notion Backlinks Creator"
version = "1.0.1"

#Configuration load
config = configparser.ConfigParser()
config.read('config.ini')

#Set logging configuration
# logging.basicConfig(level=config.get('runtime','logging'))
log = logging.getLogger(appname)
log.setLevel(config.get('runtime','logging'))

#Set screen log handler
log.addHandler(logging.StreamHandler())

#Set file log handler
log.addHandler(logging.FileHandler(config.get('runtime','logfile'))) if config.get('runtime','logfile') else None

#Notion configuration read
notion_api_token = config.get('notion', 'api_token')
notion_collection_url = config.get('notion', 'collection_url')

#Notion user preferences read
notion_reflink_section  = config.get('notion', 'reflink_section')
notion_backlink_section = config.get('notion', 'backlink_section')

#Welcome message
print(f"Welcome to {appname} v{version}")

#Connect to Notion api
print(f" connecting to Notion API")
client = NotionClient(token_v2=notion_api_token)

#Open given collection page
page = client.get_block(notion_collection_url)
print(f" loading page {page.title}")

#Verify page type, must be a collection, preferrably without filters
if page.type != 'collection_view_page':
    log.critical('The given page must be a collection (database), not a simple page! Exiting.')
    exit()


#LOAD COLLECTION AND GRAB LINKS
cv = client.get_collection_view(notion_collection_url)
print(f" loading collection {cv.parent.title}:{cv.name}")

# Define recursive function that parses the database: (IMPORTANT NOTE: This will parse all pages that are linked from pages in the database, so the effect of this script will go beyond justthe target database)

def recursive_pass(x, last_page_visited = None, context = ""):
# returns a boolean that says whether we've found a backlinks section (if yes, then we should stop scanning the page that contains us)
    global links, all_visited_pages
    new_last_page_visited = last_page_visited
    if not hasattr(x, 'title'):
        # visiting a block/page with no title.
        return {"found_backlinks_section" : False}
    log.info(f"  x [{x.id}] {x.title}")
    is_page = (x.type == "page")
    if is_page: # we're visiting a page. Make sure to change the last_page_visited and to denote that we found a new link
        if last_page_visited is not None:
            links.add((last_page_visited["title"], last_page_visited["id"], x.title, x.id, context))
            log.debug(f"   link found from ", {last_page_visited["title"]}, " to ", {x.title})
        new_last_page_visited = {"title" : x.title, "id" : x.id}
    if x.id in all_visited_pages:
        return {"found_backlinks_section" : False}
    all_visited_pages.add(x.id)
    if x.title.startswith(notion_backlink_section):
        # found backlinks section. going up and skipping rest of page.
        return {"found_backlinks_section" : True}
    # looking for links to other notion pages in this block's title:
    if x.get("properties") is not None:
        for snippet in x.get("properties")["title"]:
            if snippet[0] == "‣": # found link
                linked_node_id = snippet[1][0][1]
                linked_block = client.get_block(linked_node_id)
                recursive_pass(linked_block, last_page_visited = new_last_page_visited, context = x.title)
    # now visiting all the block's children:
    for child in x.children:
        returned_info = recursive_pass(child, new_last_page_visited)
        found_backlinks_section = returned_info["found_backlinks_section"]
        if found_backlinks_section: # found backlinks section so should stop scanning the page
            if is_page: # great, the backlinks section is the end of this page
                return {"found_backlinks_section" : False}
            else: # go back to the containing page
                return {"found_backlinks_section" : True}
    return {"found_backlinks_section" : False}
# Run the recursive function:
# Store all page links within collection (tuples: from.name, from.id, to.name, to.id)
links = set()
all_visited_pages = set()
for block in cv.collection.get_rows():
    recursive_pass(block)
#Inform what we have found
print(f"  links found: {len(links)}")

links_to_make = list(links)

#Inform if we have no backlink to create at all
if not len(links_to_make):
    print(f"  no backlinks to create")
    print(f"Done.")
    exit()
        
#Sort backlinks by source page (not really needed yet)
links_to_make.sort(key=lambda item: item[3])

def find_backlinks_section(page_id):
    page = client.get_block(page_id)

    backlinks_found = False
    last_backlink = None

    #Iterating over all page sections
    for child in page.children:
        if last_backlink is None or not backlinks_found:
            last_backlink = child

        #Test if we reached backlink section which may contains links?
        if hasattr(child, 'title') and child.title.startswith(notion_backlink_section):
            backlinks_found = True
            last_backlink = child
            continue

        #Find the last link in backlinks section
        if backlinks_found and child.type == 'page':
            last_backlink = child
            continue
    if backlinks_found:
        return last_backlink
    else:
        return None
    

#Sort backlinks by source page (not really needed yet)
links_to_make.sort(key=lambda item: item[3])

#Set style for new backlinks section name
backlink_styles = {"H1": HeaderBlock, "H2": SubheaderBlock, "H3": SubsubheaderBlock, "TEXT": TextBlock}
backlink_style = backlink_styles[config.get('notion', 'backlink_style')]

all_visited_pages_no_hyphens = [x.replace("-", "") for x in all_visited_pages]

# First remove a lot of banklinks, namely all backlinks to pages that we visited (if they should still be in, they'll get added in the next phase) as well as backlinks to pages that don't exist anymore. But keep all banklinks to pages that we haven't visited.
for page_id in all_visited_pages:
    page = client.get_block(page_id)
    last_backlink = find_backlinks_section(page_id)
    if last_backlink is None:
        continue
    started_backlinks_section = False
    list_of_children = last_backlink.children[:]
    removed_all_backlinks = True
    for child in list_of_children:
        backlink_whole_text = child.title
        only_backlink = backlink_whole_text[backlink_whole_text.find("notion.so/")+10:-2]
        if only_backlink in all_visited_pages_no_hyphens:
            child.remove()
        else:
            removed_all_backlinks = False
    if removed_all_backlinks:
        last_backlink.remove()

print(f"  creating {len(links_to_make)} backlink(s) - please wait")

# Now add all needed backlinks: (code below is very inefficient. can improve a lot but sorting in advance and changing to a depth-3 dictionary.)

for backlink_source_page in {link[3] for link in links_to_make}:
    page = client.get_block(backlink_source_page)
    last_backlink = find_backlinks_section(backlink_source_page)
    #There were no backlinks section, adding one            
    if last_backlink is None:
        log.debug(f"     {notion_backlink_section} section not found, adding")
        #We add empty space before backlinks section
        new_space_block = page.children.add_new(TextBlock, title="")
        #Then add the backlinks section with configured style (H1, H2, H3 or TEXT)
        new_backlink_block = page.children.add_new(backlink_style, title=notion_backlink_section)
        new_backlink_block.move_to(new_space_block, "after")
        last_backlink = new_backlink_block
    for backlink_target_page_id, backlink_target_page_title in {(link[1], link[0]) for link in links_to_make if link[3] == backlink_source_page}:
        log.info(f"going to backlink {page.title} to {backlink_target_page_title}")
        url_in_backlink = client.get_block(backlink_target_page_id).get_browseable_url()
        backlink_target_page_new_block = last_backlink.children.add_new(TextBlock, title="linked from [{}]({}).".format(backlink_target_page_title, url_in_backlink))
        for link in links_to_make:
            if link[3] != backlink_source_page: # only add links from the backlink_source_page
                continue
            if link[1] != backlink_target_page_id: # only add links from the backlink_source_page
                continue
            if link[4] is None or len(link[4].strip()) <= 1:
                continue                
            new_block = backlink_target_page_new_block.children.add_new(TextBlock, title=link[4])
            # TODO: add to the context the inline link mention/link-title. right now it's being dropped.
        print(f"    created backlinks from {link[2]} to {link[0]}")

print(f"Finished.")

