from dataclasses import dataclass
from typing import Callable, ClassVar, Dict, Generic, List, Type, TypeVar
from spirehdl.spirehdl_module import Component
from spirehdl.arithmetic.int_multipliers.eval.testvector_generation import Encoding


class Config():
    pass


class JsonExportConfig(Config):
    # Maps "<attr path on config>" -> "<result dict key>"
    # Example: {"cfg.mult_cfg.ppa_opt": "ppa_cls_name"}
    json_export_fields: ClassVar[Dict[str, str]] = {}

@dataclass(frozen=True)
class MultConfig(Config):
    ppg_cls: type
    ppa_cls: type
    fsa_cls: type
    optim_type: str
    a_w: int
    b_w: int
    a_encoding: Encoding = Encoding.unsigned
    b_encoding: Encoding = Encoding.unsigned


@dataclass(frozen=True)
class AdderConfig(Config):
    fsa_cls: type
    optim_type: str
    a_w: int
    b_w: int
    signed_a: bool
    signed_b: bool
    full_output_bit: bool = False

C = TypeVar("C", bound="Config")
@dataclass(frozen=True)
class InstanceConfig(Generic[C]):
    impl_cls: Type[Component]
    config: C
    def gen_instance(self) -> Component:
        return self.impl_cls(**self.config.__dict__)
    
@dataclass(frozen=True)
class VecConfig:
    num_vectors: int
    seed: int = 42
    func: Callable = None  # Function to generate vectors
    args: dict = None  # Additional arguments for the function
