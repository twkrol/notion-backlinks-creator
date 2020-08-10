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

def recursive_pass(x, last_page_visited = None):
# returns a boolean that says whether we've found a backlinks section (if yes, then we should stop scanning the page that contains us)
    new_last_page_visited = last_page_visited
    if not hasattr(x, 'title'):
        # visiting a block/page with no title.
        return False
    log.info(f"  x [{x.id}] {x.title}")
    is_page = (x.type == "page")
    if is_page: # we're visiting a page. Make sure to change the last_page_visited and to denote that we found a new link
        if last_page_visited is not None:
            links.add((last_page_visited["title"], last_page_visited["id"], x.title, x.id))
            log.debug(f"   link found from ", {last_page_visited["title"]}, " to ", {x.title})
        new_last_page_visited = {"title" : x.title, "id" : x.id}
    if x.id in already_visited:
        return False
    already_visited.add(x.id)
    if x.title.startswith(notion_backlink_section):
        # found backlinks section. going up and skipping rest of page.
        return True
    # looking for links to other notion pages in this block's title:
    if x.get("properties") is not None:
        for snippet in x.get("properties")["title"]:
            if snippet[0] == "‣": # found link
                linked_node_id = snippet[1][0][1]
                linked_block = client.get_block(linked_node_id)
                recursive_pass(linked_block, new_last_page_visited)
    # now visiting all the block's children:
    for child in x.children:
        found_backlinks_section = recursive_pass(child, new_last_page_visited)
        if found_backlinks_section: # found backlinks section so should stop scanning the page
            if is_page: # great, the backlinks section is the end of this page
                return False
            else: # go back to the containing page
                return True            
    return False
# Run the recursive function:
# Store all page links within collection (tuples: from.name, from.id, to.name, to.id)
links = set()
already_visited = set()
for block in cv.collection.get_rows():
    recursive_pass(block)
#Inform what we have found
print(f"  links found: {len(links)}")

#Function for testing link's mutual pair in the links collection
def hasPair(link, links):
    for pair in links:
        if pair[3] == link[1] and pair[1] == link[3]:
            return True
    return False

#Store all mutual page links we have to create (tuples: from.name, from.id, to.name, to.id)
links_to_make = []

#LOOKING FOR LINKS WITHOUT MUTUAL LINKS
for link in links:
    if not hasPair(link, links):
        links_to_make.append(link)
        log.debug(f"  no mutual link from {link[0]} to {link[2]}")

#Inform if we have no backlink to create at all
if not len(links_to_make):
    print(f"  no backlinks to create")
    print(f"Done.")
    exit()
        
#Sort backlinks by source page (not really needed yet)
links_to_make.sort(key=lambda item: item[3])

print(f"  creating {len(links_to_make)} backlink(s) - please wait")

#Set style for new backlinks section name
backlink_styles = {"H1": HeaderBlock, "H2": SubheaderBlock, "H3": SubsubheaderBlock, "TEXT": TextBlock}
backlink_style = backlink_styles[config.get('notion', 'backlink_style')]

#Iterating all backlinks to create
for link in links_to_make:
    page = client.get_block(link[3])
    log.info(f"    seeking place to backlink {page.title} to {link[0]}")
    
    backlinks_found = False
    last_backlink = None
    
    #Iterating over all page sections
    for child in page.children:
        log.debug(f"    inside child {getattr(child, 'title', child.type)}")
        
        #Set last known page element
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

    #There were no backlinks section, adding one            
    if not backlinks_found:
        log.debug(f"     {notion_backlink_section} section not found, adding")
        #We add empty space before backlinks section
        new_space_block = page.children.add_new(TextBlock, title="")
        #Then add the backlinks section with configured style (H1, H2, H3 or TEXT)
        new_backlink_block = page.children.add_new(backlink_style, title=notion_backlink_section)
        new_backlink_block.move_to(new_space_block, "after")
        last_backlink = new_backlink_block

    #Actually creating the backlink
    new_block = page.children.add_alias(client.get_block(link[1]))
    print(f"    created backlink from {link[2]} to {link[0]}")

print(f"Finished.")
