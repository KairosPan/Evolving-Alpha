# youzi_web/features/strategy/__init__.py — 产品核心件:策略 + agent
from youzi_web.features.strategy.router import router
from youzi_web.registry import Feature, SubNavItem

feature = Feature(
    id="strategy", label="策略", icon="📜", router=router,
    subnav=[
        SubNavItem("技能库", "/strategy/skills"),
        SubNavItem("纪律与心法", "/strategy/doctrine"),
        SubNavItem("周期状态机", "/strategy/cycle"),
        SubNavItem("决策驾驶舱", "/decision/cockpit"),
        SubNavItem("三方对比", "/research/compare"),
        SubNavItem("精炼时间线", "/research/refine"),
        SubNavItem("决策轨迹", "/research/trajectory"),
        SubNavItem("进化史", "/strategy/evolution", enabled=False),
    ],
)
