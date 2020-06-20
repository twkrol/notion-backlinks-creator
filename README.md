# notion-backlinks-creator
Automates creating backlinks to pages within collections. Helps maintain zettelkasten references.

# When would you like to use this tool
In case you have a collection of pages in Notion and you use the 'Link to page' feature to link one page to another, you may want to automatically backlink the latter page to the referencing one. This is usefull if you maintain a zettelkasten store where linking forward and backward is essential.

# Getting started
Follow these steps for pipenv:
1. Download this python app
2. Open virtualenv: <code>pipenv shell</code>
3. Install referenced libraries: <code>pipenv install</code>
4. Copy <code>config.ini.example</code> to <code>config.ini</code>
5. Edit config.ini (your api_token and collection_page_url are mandatory)
6. Run application: <code>python app.py</code>

# Disclaimer
This tool can, and probably will modify your Notion data! It was not extensivelly tested, so any errors may occur and you may lost your data.
For the first time run it on a simple demo collection to avoid any unwanted data modifications.
I'm not responsible for any damages it may cause.
*You have been warned*
