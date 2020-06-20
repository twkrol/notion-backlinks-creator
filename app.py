from notion.client import NotionClient
from notion.block import *

notion_token="1360dd09a8015eea4a08c1807a35d493578dce6f976f60e192aa0c88cab770f3f85fe4b83033be33c5e7b11ddaf6ab88efaba328dcdf81481639e09280576610714031c7f414cc1e8228d6f60b4d"
notion_page_url = "https://www.notion.so/a5fb54d9f47545819ff0c5c26b0ca25f?v=c4bed1522240477c9407675a177d7aeb"

print("Starting Notion client v0.0.1")

client = NotionClient(token_v2=notion_token)

page = client.get_block(notion_page_url)

print(f"parent of this page is {page.parent.title}")
print(f" page title is:{page.title}, type:{page.type}")


# Algorytm:
# - zrób tablicę linków: dest, skąd
# - iteruj po wszystkich rekordach
# - dla każdego rekordu weź wszystkie linki które w sobie zawiera
#   - dla każdego z linków zapamiętaj go w tablicy: dokąd prowadzi i z jakiego to jest rekordu
# - iteruj po tablicy linków i dla każdej pary [dest,skąd] sprawdź czy istnieje para odwrotna tzn. jeśli ktoś linkuje do mnie to czy ja do niego też?
#   - jeśli nie, utwórz na stronie dest reflinka do skąd /i może trzeba dopisać do tabeli linków na wszelki wypadek?/

# TODO: przy dodawaniu wyszukać sekcję Backlinks, a jeśli jej nie ma to utworzyć, i dopiero pod nią tworzyć te backlinks_exist

if page.type != 'collection_view_page':
    print('strona z artykułami do linkowania musi być kolekcją (bazą danych)')
    exit()

print(f"\nOtwieram bazę {page.title}")
cv = client.get_collection_view(notion_page_url)

links = []  #list of tuples (from.name, from.id, to.name, to.id)

#SZUKAMY REFLINKÓW I BACKLIKÓW

for row in cv.collection.get_rows():
    section = None
    print(f"\nrow title:{row.title}, id:{row.id}")
    for child in row.children:
        # print(f" section:{section}, child.type:{child.type}, child.title:{getattr(child, 'title', child.type)}")

        #gdzie jesteśmy - czy to początek sekcji Reflinks lub Backlinks?
        if hasattr(child, 'title') and (child.title.startswith('#Reflinks') or child.title.startswith('#Backlinks')):
            section = 'links'
            continue

        #gdzie jesteśmy - jeśli w sekcji Reflinks lub Backlinks nie ma typu page (linku do strony) to to nie jest juz sekcja z linkami
        if section == 'links' and child.type != 'page':
            section = None
            continue

        #wyciągamy linki do stron z reflinks
        if section == 'links' and child.type == 'page':
            links.append((row.title, row.id, child.title, child.id))


print(f"Znaleziono takie linki:")
for link in links:
    print(f" z {link[0]} do {link[2]}")


def hasPair(link, links):
    for pair in links:
        if pair[3] == link[1] and pair[1] == link[3]:
            return True
    return False


#SZUKAMY BACKLINKÓW DO UZUPEŁNIENIA
links_to_make = []

for x, link in enumerate(links):
    # print(f"{x} has pair: {hasPair(link, links)}")
    if not hasPair(link, links):
        links_to_make.append(link)
        print(f" link {x} nie ma pary: {link[1]} do {link[3]}")
    else:
        print(f" link {x} ma parę")


for link in links_to_make:
    print(f"muszę wygenerować backlink do pary z {link[0]} do {link[2]}")

#sortujemy po stronie która będzie źródłem
links_to_make.sort(key=lambda item: item[3])

for link in links_to_make:
    page = client.get_block(link[3])
    print(f"otwieram {page.title}")
    
    backlinks_found = False
    last_backlink = None
    
    for child in page.children:
        # print(f" jestem w child {child.title if hasattr(child, 'title') else 'no-title'}")
        print(f" jestem w child {getattr(child, 'title', child.type)}")
        
        if last_backlink is None or not backlinks_found:
            last_backlink = child

        #gdzie jesteśmy - czy to początek sekcji Reflinks lub Backlinks?
        if hasattr(child, 'title') and child.title.startswith('#Backlinks'):
            backlinks_found = True
            last_backlink = child
            continue

        if backlinks_found and child.type == 'page':
            last_backlink = child
            continue
            
    if not backlinks_found:
        print(f" muszę dodać sekcję #Backlinks bo nie ma")
        #TODO tutaj dodac tworzenie sekcji #Backlinks i ustawić last_backlink na tą sekcję
        new_space_block = page.children.add_new(TextBlock, title="")
        new_backlink_block = page.children.add_new(SubsubheaderBlock, title="#Backlinks")
        new_backlink_block.move_to(new_space_block, "after")
        last_backlink = new_backlink_block

    print(f" dodaję nowy backlink z {link[2]} do {link[0]}")
    new_block = page.children.add_alias(client.get_block(link[1]))
    # new_block.move_to(last_backlink, "after")

# print(f"Znaleziono takie linki:")
# for link in links:
#     print(f" z {link[0]} do {link[1]}")
