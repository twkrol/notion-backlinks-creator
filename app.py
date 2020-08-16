import configparser
import logging
from notion.client import NotionClient
from notion.block import HeaderBlock, SubheaderBlock, SubsubheaderBlock, TextBlock, PageBlock
from notion.utils import InvalidNotionIdentifier
from requests import HTTPError
from collections import defaultdict

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
main_page = client.get_block(notion_collection_url)
main_page_spaceid = main_page.space_info["spaceId"]
print(f" loading page {main_page.title}")

# Let's define functions that deal with timeouts (TODO: merge all of these to one function, to avoid code duplication)
# SAMPLE TIMEOUT: HTTPError: 504 Server Error: Gateway Time-out for url: https://www.notion.so/api/v3/loadPageChunk

def notion_get_page(page_id, max_tries = 10):
    global client
    tries = 0
    while True:
        try:
            return client.get_block(page_id)
        except HTTPError:
            tries += 1
            if tries > max_tries:
                raise

def notion_get_attr(x, attr, max_tries = 10):
    tries = 0
    while True:
        try:
            result = getattr(x, attr)
            return result
        except HTTPError:
            tries += 1
            if tries > max_tries:
                raise

def notion_has_attr(x, attr, max_tries = 10):
    tries = 0
    while True:
        try:
            result = hasattr(x, attr)
            return result
        except HTTPError:
            tries += 1
            if tries > max_tries:
                raise

def notion_get_spaceid(x, max_tries = 10):
    tries = 0
    while True:
        try:
            result = x.space_info["spaceId"]
            return result
        except HTTPError:
            tries += 1
            if tries > max_tries:
                raise
                
def notion_get_rich_title(x, max_tries = 10):
    tries = 0
    while True:
        try:
            x_prop = x.get("properties")                       
            if x_prop is None or "title" not in x_prop:
                return None
            return x_prop["title"]
        except HTTPError:
            tries += 1
            if tries > max_tries:
                raise
                
def find_containing_page(x): # recursively go to parent until you find a notion page
    if notion_get_attr(x, "type") == "page":
        return x
    else:
        return find_containing_page(notion_get_attr(x, "parent"))

def extract_linked_pages_from_rich_title(rich_title):
# tnis function gets a rich title and finds various urls and linkd entities in it.
# note that the rich title is simply a nested python list. each element of the first layer is a component of the title
    if isinstance(rich_title, list):
        return sum([extract_linked_pages_from_rich_title(x) for x in rich_title], [])
    assert isinstance(rich_title, str)
    if len(rich_title) == 36 and rich_title[8] == "-" and rich_title[13] == "-" and rich_title[18] == "-" and rich_title[23] == "-": # probably found a block id
        linked_block = notion_get_page(rich_title)
        linked_page = find_containing_page(linked_block)
        return [linked_page]
    result = []
    all_links = rich_title.split("ww.notion.so/")[1:]
    for s in all_links:
        actual_link = "https://www.notion.so/" + s.split()[0].split("'")[0].split("\"")[0]
        try:
            linked_block = client.get_block(actual_link)
            linked_page = find_containing_page(linked_block)
            result.append(linked_page)
        except InvalidNotionIdentifier:
            print("failed to retrieve block corresponding to the following URL, so skipping it: ", actual_link)
    return result



# Define recursive function that parses the database: (IMPORTANT NOTE: This will parse all pages that are linked from pages in the database, so the effect of this script will go beyond justthe target database)

def recursive_pass(x, last_node_visited_id, last_page_visited = None, context = None):
# returns a boolean that says whether we've found a backlinks section (if yes, then we should stop scanning the page that contains us)
# this function's goal is mostly to build the dictionary links_to_make
    # this function uses the following global variables: client, links_to_make, all_visited_pages, main_page_spaceid
    
    # Housekeeping:
    if context is None:
        context = ""
    new_last_page_visited = last_page_visited # for now.
    new_context = context # for now.
    if not notion_has_attr(x, 'title'):
        # visiting a block/page with no title, such as a separator block
        return {"found_backlinks_section" : False, "context" : context}
    x_id = notion_get_attr(x, "id")
    x_title = notion_get_attr(x, "title")
    if notion_has_attr(x, "title_plaintext"):
        x_title_plaintext = notion_get_attr(x, "title_plaintext")
    else:
        x_title_plaintext = notion_get_attr(x, "title")
    x_type = notion_get_attr(x, "type")
    x_children = notion_get_attr(x, "children")
    log.info(f"  x [{x_id}] {x_title}")

    x_spaceid = notion_get_spaceid(x)
    if x_spaceid != main_page_spaceid:
        print("got to a page titled", x_title_plaintext, "outside of the specified collection's spaceid; skipping it.")
        return {"found_backlinks_section" : False, "context" : context}    
    
    context_to_return = context
    if x_type == "page": # we're visiting a page. Make sure to change the last_page_visited and to denote that we found a new link
        if last_page_visited is not None:
            if len(x_children) > 0: # don't add backlinks to empty pages
#            print(f"   link found from ", {last_page_visited["title"]}, " to ", {x_title})
#            print(x_id, x_title, last_page_visited["id"], last_page_visited["title"], last_node_visited_id, context)
                links_to_make[(x_id, x_title)][(last_page_visited["id"], last_page_visited["title"])].add((last_node_visited_id, context))
                log.debug(f"   link found from ", {last_page_visited["title"]}, " to ", {x_title})
        new_last_page_visited = {"title" : x_title, "id" : x_id}
        new_context = ""
              
    # if we visited this page before, then we shouldn't scan it now, since we've scanned it before:
    if x_id in all_visited_pages:
        return {"found_backlinks_section" : False, "context" : context}
    all_visited_pages.add(x_id)
    if x_title.startswith(notion_backlink_section):
        # found backlinks section. signaling to above to stop scanning the page
        assert x_type != "page"
        return {"found_backlinks_section" : True, "context" : context}
    
    # looking for links to other notion pages in this block's title:
    rich_title = notion_get_rich_title(x)
    current_context = x_title_plaintext
    context_to_pass = new_context[-80:] + " \\ " + x_title_plaintext
    if rich_title is not None:
        for linked_page in extract_linked_pages_from_rich_title(rich_title):
            recursive_pass(linked_page, x_id, last_page_visited = new_last_page_visited, context = context_to_pass) # when this function is called, linked_page is always a page, so this function call will always cause at least one new item to be created in links_to_make
    # now visiting all the block's children:
    context_to_pass = context_to_pass[-90:]
    for child in x_children:              
        returned_info = recursive_pass(child, x_id, new_last_page_visited, context = context_to_pass)
        if returned_info["context"] != "":
            context_to_pass = returned_info["context"][-90:]
        found_backlinks_section = returned_info["found_backlinks_section"]
        if found_backlinks_section: # found backlinks section so should stop scanning the page
            if x_type == "page": # great, the backlinks section is the end of this page
                return {"found_backlinks_section" : False, "context" : ""}
            else: # go back to the containing page
                return {"found_backlinks_section" : True, "context" : context_to_pass}
    context_to_return = context_to_pass if x_type != "page" else ""
    return {"found_backlinks_section" : False, "context" : context_to_return}
#Verify page type, must be a collection, preferrably without filters
if main_page.type != 'collection_view_page':
    log.critical('The given page must be a collection (database), not a simple page! Exiting.')
    exit()
    
#LOAD COLLECTION AND GRAB LINKS
cv = client.get_collection_view(notion_collection_url)
print(f" loading collection {cv.parent.title}:{cv.name}")
# Run the recursive function:
# Store all page links within collection (tuples: from.name, from.id, to.name, to.id)
links_to_make = defaultdict(lambda : defaultdict(lambda: set()))
all_visited_pages = {main_page.id}
for block in cv.collection.get_rows():
    recursive_pass(block, main_page.id, last_page_visited = {"title" : main_page.title, "id" : main_page.id})
#Inform what we have found


#Inform if we have no backlink to create at all
if not len(links_to_make):
    print(f"  no backlinks to create")
    print(f"Done.")
    exit()
        

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
        if len(page.children) >= 1:
            last_block = page.children[-1]
            if len(last_block.title.strip()) == 0 and len(last_block.children) == 0:
                last_block.remove()


# Now add all needed backlinks:
for source in links_to_make:
    backlink_source_page_id, backlink_source_page_title = source
    page = client.get_block(backlink_source_page_id)
    last_backlink = find_backlinks_section(backlink_source_page_id)
    #There were no backlinks section, adding one            
    if last_backlink is None:
        log.debug(f"     {notion_backlink_section} section not found, adding")
        #We add empty space before backlinks section
        new_space_block = page.children.add_new(TextBlock, title="")
        #Then add the backlinks section with configured style (H1, H2, H3 or TEXT)
        new_backlink_block = page.children.add_new(backlink_style, title=notion_backlink_section)
        new_backlink_block.move_to(new_space_block, "after")
        last_backlink = new_backlink_block
    for target in links_to_make[source]:
        backlink_target_page_id, backlink_target_page_title = target
        log.info(f"going to backlink {page.title} to {backlink_target_page_title}")
        url_in_backlink = client.get_block(backlink_target_page_id).get_browseable_url()

        # deal with the special case that backlink_target_page_title includes a link:
        while ("(http" in backlink_target_page_title): # TODO this is probably somewhat buggy. Need to improve it. The point is that the backlink creator behaves strangely when linking to pages whose title contains a link
            startpoint = backlink_target_page_title.find("(http")
            endpoint = backlink_target_page_title[startpoint:].find(")") + startpoint + 1
            backlink_target_page_title = backlink_target_page_title[:startpoint] + backlink_target_page_title[endpoint:]
        backlink_target_page_title = backlink_target_page_title.replace("[", "").replace("]", "")

        # add the link:
        backlink_target_page_new_block = last_backlink.children.add_new(TextBlock, title="linked from [{}]({}).".format(backlink_target_page_title, url_in_backlink))
        # add contexts from all the appearances of that link:
        for direct_id_of_linking_node, context in links_to_make[source][target]:
            try:
                new_string = "[(direct linking block)]({}).".format(client.get_block(direct_id_of_linking_node).get_browseable_url())
            except AttributeError:
                new_string = ""
            new_string += context
            new_block = backlink_target_page_new_block.children.add_new(TextBlock, title=new_string)
        print(f"    created backlinks from {backlink_source_page_title} to {backlink_target_page_title}")

print(f"Finished.")