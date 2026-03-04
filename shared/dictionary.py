# Single source of account data
accounts_by_key = {
    "98900/1575456EUR": {'name': "Ouders", 'id': "zHBpid7mvLiq476MPFcX7TKO2Ei1gNDDWsz-S0ZDAzA="},
    "98900/1622448EUR": {'name': "Kinderen", 'id': "||I-eOXemnJUt|T53kVP|qDxTqPUysN36UILHCsJVlc="},
    "98900/1599306EUR": {'name': "AutoInvest", 'id': "s2sy3q0vZkcNK0-qLEFrN-jN-XLgBpFHrN7zVZcFJK4="}
}

# Build secondary lookup dictionaries
accounts_by_name = {v['name']: {'key': k, 'id': v['id']} for k, v in accounts_by_key.items()}
accounts_by_id = {v['id']: {'key': k, 'name': v['name']} for k, v in accounts_by_key.items()}
