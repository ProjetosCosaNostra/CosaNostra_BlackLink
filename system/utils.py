# utilidades gerais do BlackLink
def load_config():
    import json
    with open('blacklink_config.json', 'r', encoding='utf8') as f:
        return json.load(f)
