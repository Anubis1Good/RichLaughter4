base_tf = 5

# Формат настройки тикера: (lot, tf)
pc_groups = {
    'MAIN_PC': {
        'LiteInvest:stockLI': {
            'AFLT': (1, base_tf),
            'ALRS': (1, base_tf),
            'ASTR': (1, base_tf),
            'MTLR': (1, base_tf),
        },
    },
    'SECOND_PC': {
        'LiteInvest:stockLI': {
            'SBER': (1, base_tf),
            'GAZP': (1, base_tf),
        },
    },
}
