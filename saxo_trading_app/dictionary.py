uic_dict = {
    50629: "ETF MSCI World",
    1636: "ASML",
    36465: "WisdomTree GOLD",
    10307078: "Pinduoduo",
    773599: "Google",
    36962: "EVS",
    261: "MSFT",
    8953538: "Lithium",
    37609176: "NOVO",
    43337: "Lotus",
    25449122: "Bitcoin ETF",
    6460562: "S&P500 ETF",
    46634080: "ASR opties"
}

# Single source of account data
accounts_by_key = {
    "98900/1575456EUR": {'name': "Ouders", 'id': "zHBpid7mvLiq476MPFcX7TKO2Ei1gNDDWsz-S0ZDAzA="},
    "98900/1622448EUR": {'name': "Kinderen", 'id': "||I-eOXemnJUt|T53kVP|qDxTqPUysN36UILHCsJVlc="},
    "98900/1599306EUR": {'name': "AutoInvest", 'id': "s2sy3q0vZkcNK0-qLEFrN-jN-XLgBpFHrN7zVZcFJK4="}
}

# Build secondary lookup dictionaries
accounts_by_name = {v['name']: {'key': k, 'id': v['id']} for k, v in accounts_by_key.items()}
accounts_by_id = {v['id']: {'key': k, 'name': v['name']} for k, v in accounts_by_key.items()}
