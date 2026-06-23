"""EndpointSpec 与 hook Protocol 定义。

设计要点(对应 v3 文档 §3.4/§3.5/§3.6):
  - EndpointSpec 是 ``@final`` + ``frozen=True`` 的 dataclass:
      * @final:不允许继承(拉式收集用 ``type(attr) is EndpointSpec`` 严格匹配)
      * frozen=True:实例不可变,锁内取出后到锁外用是安全的(无 TOCTOU 风险)
  - ``__post_init__`` 强校三件事:
      a. 必填字段类型(``request``/``responses`` 必须是 BaseModel 子类或 None)
      b. 契约保真护栏(model_config 必须 ``extra="forbid"``、禁用清单全关)
      c. 错误信息对作者友好(写明原因 + 修复建议)
  - 三个 ``runtime_checkable Protocol``(MockHook/ValidateHook/BuildRequestHook)
    本期不实装,签名本期定;实现 hook 的作者用 ``isinstance(spec.mock_hook, MockHook)``
    即可校验协议
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, final, runtime_checkable

from pydantic import BaseModel


# ════════════════════════════════════════════════════════════════════════════
# 三个 hook Protocol(本期不实装,签名本期定 —— v3 §3.7)
# ════════════════════════════════════════════════════════════════════════════

@runtime_checkable
class MockHook(Protocol):
    """被 mock 响应生成时调用,产出完整 response body dict。

    返回 ``None`` = 走通用 mock 逻辑(用 spec.responses[status] + Field(examples=) 填字段)。
    返回 ``dict`` = 用该 dict 作为响应 body,跳过通用填充。
    """

    def __call__(self, spec: "EndpointSpec", request_payload: dict) -> dict | None: ...


@runtime_checkable
class ValidateHook(Protocol):
    """被 response 校验时调用,在 extra=forbid 之后、断言策略之前。

    hook 内 raise 即视为该次响应校验失败。
    """

    def __call__(
        self, spec: "EndpointSpec", response_payload: dict, status: int
    ) -> None: ...


@runtime_checkable
class BuildRequestHook(Protocol):
    """被请求构建时调用,在 model_validate 之后、httpx 发出之前。

    返回值替换原 body dict,让 hook 可以做"按系统特异规则"重组 body。
    """

    def __call__(self, spec: "EndpointSpec", values: dict) -> dict: ...


# ════════════════════════════════════════════════════════════════════════════
# 契约保真禁用清单(v3 §5.4)
# ════════════════════════════════════════════════════════════════════════════

# 这些 Pydantic 选项会改写 wire 格式,契约模型必须全部关闭。
# _assert_safe_model 在 spec 注册期逐一检查。
_FORBIDDEN_CONFIG_KEYS: tuple[tuple[str, str], ...] = (
    ("str_strip_whitespace", "会把 ' abc ' 改成 'abc',破坏 wire 格式"),
    ("coerce_numbers_to_str", "会在 55 / '55' 之间互转,影响类型判断"),
    ("use_enum_values", "会把 Enum 实例替换为字面值,改变 wire 表示"),
)


# ════════════════════════════════════════════════════════════════════════════
# EndpointSpec 主体
# ════════════════════════════════════════════════════════════════════════════

@final
@dataclass(frozen=True)
class EndpointSpec:
    """单个 endpoint 的契约描述。数据为主、hook 为辅,默认走通用行为。

    字段分组:
      数据(必填):method / path
      数据(可空):request(GET 类允许 None) / responses(允许空 dict)
      文档元数据(喂 mock / 后期 OpenAPI 导出):summary / description / tags / auth_required
      预留槽位(本期不实装,Optional=None,后期启用零破坏):
        default_response / response_union
      能力 hook(本期不实装,None = 走通用行为):mock_hook / validate_hook / build_request_hook
    """

    # —— 数据(必填)——
    method: str
    path: str

    # —— 数据(可选)——
    request: type[BaseModel] | None = None
    responses: dict[int, type[BaseModel]] = field(default_factory=dict)

    # —— 文档元数据 ——
    summary: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    auth_required: bool = False

    # —— 预留槽位(本期不实装)——
    default_response: type[BaseModel] | None = None
    response_union: dict[int, tuple[type[BaseModel], ...]] = field(default_factory=dict)

    # —— 能力 hook(本期不实装,None = 走通用行为)——
    mock_hook: MockHook | None = None
    validate_hook: ValidateHook | None = None
    build_request_hook: BuildRequestHook | None = None

    def __post_init__(self) -> None:
        # (a) 必填字段类型校验
        if not isinstance(self.method, str) or not self.method:
            raise TypeError(
                f"EndpointSpec({self.path!r}): method 必须是非空字符串,实际 "
                f"{type(self.method).__name__}: {self.method!r}"
            )
        if not isinstance(self.path, str) or not self.path:
            raise TypeError(
                f"EndpointSpec: path 必须是字符串(必填),实际 {type(self.path).__name__}: {self.path!r}"
            )
        if self.request is not None and not _is_basemodel_subclass(self.request):
            raise TypeError(
                f"EndpointSpec({self.path}): request 必须是 BaseModel 子类或 None,"
                f"实际 {self.request!r}"
            )
        for code, model in self.responses.items():
            if not isinstance(code, int):
                raise TypeError(
                    f"EndpointSpec({self.path}): responses 的 key 必须是 int 状态码,"
                    f"实际 {type(code).__name__}: {code!r}"
                )
            if not _is_basemodel_subclass(model):
                raise TypeError(
                    f"EndpointSpec({self.path}): responses[{code}] 必须是 BaseModel 子类,"
                    f"实际 {model!r}"
                )
        if self.default_response is not None and not _is_basemodel_subclass(self.default_response):
            raise TypeError(
                f"EndpointSpec({self.path}): default_response 必须是 BaseModel 子类或 None,"
                f"实际 {self.default_response!r}"
            )
        for code, models in self.response_union.items():
            if not isinstance(code, int):
                raise TypeError(
                    f"EndpointSpec({self.path}): response_union 的 key 必须是 int 状态码"
                )
            if not isinstance(models, tuple) or not all(_is_basemodel_subclass(m) for m in models):
                raise TypeError(
                    f"EndpointSpec({self.path}): response_union[{code}] 必须是 "
                    f"(BaseModel 子类, ...) 元组,实际 {models!r}"
                )

        # (b) 契约保真护栏(v3 §3.6)
        if self.request is not None:
            _assert_safe_model(self.request, f"EndpointSpec({self.path}).request")
        for code, model in self.responses.items():
            _assert_safe_model(model, f"EndpointSpec({self.path}).responses[{code}]")
        if self.default_response is not None:
            _assert_safe_model(
                self.default_response, f"EndpointSpec({self.path}).default_response"
            )

    # ── 文档与 introspection 辅助(供 mock/contract check 工具使用)──

    def response_models(self) -> dict[int, type[BaseModel]]:
        """返回 ``{status: model}``,与 ``self.responses`` 同形(浅拷贝)。"""
        return dict(self.responses)

    def has_request(self) -> bool:
        return self.request is not None


# ════════════════════════════════════════════════════════════════════════════
# 内部辅助
# ════════════════════════════════════════════════════════════════════════════

def _is_basemodel_subclass(obj: Any) -> bool:
    """判断 obj 是不是 BaseModel 子类(type 且 issubclass)。"""
    return isinstance(obj, type) and issubclass(obj, BaseModel)


def _get_model_config(cls: type[BaseModel]) -> Any:
    """安全获取 Pydantic 模型的 model_config,容忍未声明的情况。"""
    return getattr(cls, "model_config", None)


def _assert_safe_model(cls: type[BaseModel], role: str) -> None:
    """契约保真护栏:model 必须不会改写 wire 格式。

    检查项:
      1. 必须声明 ``model_config``
      2. ``model_config['extra']`` 必须为 ``"forbid"``
      3. 禁用清单(``str_strip_whitespace`` / ``coerce_numbers_to_str`` /
         ``use_enum_values``)必须全部为 False / None

    任一项不符则抛 TypeError,信息含:原因 + 修复建议 + 文档引用。
    """
    cfg = _get_model_config(cls)
    if cfg is None:
        raise TypeError(
            f"{cls.__name__}.{role}: 缺少 model_config。"
            f"契约模型必须显式声明 model_config = ConfigDict(extra='forbid', ...)。"
            f"详见 docs/modules/contract.md §契约保真。"
        )

    # extra 必须是 "forbid"
    extra = cfg.get("extra") if hasattr(cfg, "get") else None
    if extra != "forbid":
        raise TypeError(
            f"{cls.__name__}.{role}: model_config['extra'] 必须为 'forbid',"
            f"契约模型不允许默默吞掉未知字段(避免字段被静默删除)。"
            f"当前值: {extra!r}。修复:在 model_config 中加 extra='forbid'。"
        )

    # 禁用清单
    for forbidden_key, why in _FORBIDDEN_CONFIG_KEYS:
        val = cfg.get(forbidden_key) if hasattr(cfg, "get") else None
        if val:  # True / 非 None 都算开启
            raise TypeError(
                f"{cls.__name__}.{role}: model_config['{forbidden_key}'] 必须关闭。"
                f"原因:{why}。当前值: {val!r}。"
            )


__all__ = [
    "EndpointSpec",
    "MockHook",
    "ValidateHook",
    "BuildRequestHook",
]
