# youzi_web/features/account/__init__.py — 账户(数据源=youzi/store 运营 7 表;组装序 ③ 点亮)
from youzi_web.features.account.router import router
from youzi_web.registry import Feature, SubNavItem

feature = Feature(
    id="account", label="账户", icon="💰", router=router,
    subnav=[SubNavItem("总览", "/account/overview")],
)
