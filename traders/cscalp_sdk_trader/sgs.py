base_tf = 5
"""
Для парных роботов обязательно указывать оба инструмента. Просто второй можно указать здесь, но не указывать в bot_on_ticker или указать там BaseTE
"""
# Формат настройки тикера: (lot, tf)
pc_groups = {
    'MAIN_PC': {
        'LiteInvest:stockLI': {
            'AFLT': (1, base_tf),
            'ALRS': (1, base_tf),
            'ASTR': (1, base_tf),
            'MTLR': (5, base_tf),
        },
    },
    'SECOND_PC': {
        'LiteInvest:stockLI': {
            'SBER': (1, base_tf),
            'APTK': (1, base_tf),
        },
    },
}
