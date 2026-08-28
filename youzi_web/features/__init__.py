# youzi_web/features/__init__.py — 三大件 IA:市场 / 策略(核心)/ 账户
from youzi_web.features.market import feature as market_feature
from youzi_web.features.strategy import feature as strategy_feature
from youzi_web.features.account import feature as account_feature

FEATURES = [market_feature, strategy_feature, account_feature]
