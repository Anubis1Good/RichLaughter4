from traders.cscalp_sdk_trader.CscalpClient import CscalpClient
c = CscalpClient()
c.subscribe("LiteInvest:stockLI", ["VTBR"])
print(c.get_position("LiteInvest:stockLI", "VTBR"))
