from paimenos.i18n import t
CATEGORIES = [('all', t('Alles')), ('webapps', 'Webapps'), ('games', t('Spiele')), ('productive', t('Produktiv'))]
GAME_IDS = { 'gcompris', 'supertux', 'supertuxkart', 'minetest', 'luanti', 'hedgewars', 'frozen-bubble', 'pingus', 'secret-maryo-chronicles'}
def app_category(item):
    if item.get('id') == 'poweroff':
        return None
    if item.get('category') in ('webapps', 'games', 'productive'):
        return item['category']
    if item.get('type') == 'webapp':
        return 'webapps'
    if item.get('emulator') or item.get('id') in GAME_IDS:
        return 'games'
    return 'productive'
def available_categories(items):
    present = {app_category(item) for item in items} - {None}
    return ['all'] + [key for key, label in CATEGORIES[1:] if key in present]
def filter_category(items, category):
    return [item for item in items if category == 'all' or item.get('id') == 'poweroff' or app_category(item) == category]
