from traders.cscalp_sdk_trader.CscalpClient import CscalpClient
c = CscalpClient()
c.subscribe("LiteInvest:stockLI", ["APTK"])
print("POS:", c.get_position("LiteInvest:stockLI", "APTK"))
print("ORDERS:", c.get_orders("LiteInvest:stockLI", "APTK"))
