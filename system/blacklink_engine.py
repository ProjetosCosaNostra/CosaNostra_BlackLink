# ============================================
# COSANOSTRA BLACKLINK - ENGINE
# Núcleo do gerador de links profissionais
# ============================================

import json
import os

def load_config():
    with open('blacklink_config.json', 'r', encoding='utf8') as f:
        return json.load(f)

def gerar_link_curto(nome: str):
    nome = nome.lower().replace(' ', '-')
    return f"https://black.link/{nome}"

def criar_blacklink(nome, descricao='', instagram='', tiktok='', youtube='', telegram=''):
    link_curto = gerar_link_curto(nome)

    data = {
        "nome": nome,
        "descricao": descricao,
        "links": {
            "instagram": instagram,
            "tiktok": tiktok,
            "youtube": youtube,
            "telegram": telegram
        },
        "blacklink": link_curto
    }

    # Salvar JSON do usuário
    output_path = f"blacklink_{nome}.json"
    with open(output_path, 'w', encoding='utf8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    return link_curto

if __name__ == '__main__':
    print('BlackLink Engine carregado.')
