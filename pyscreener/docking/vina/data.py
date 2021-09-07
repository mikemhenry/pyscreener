from dataclasses import dataclass
from enum import auto, Enum
from pathlib import Path
import shlex
from typing import Mapping, Optional, Tuple, Union

from pyscreener.exceptions import InvalidResultError, NotSimulatedError
from pyscreener.utils import ScoreMode

class Software(Enum):
    def _generate_next_value_(name, start, count, last_values):
        return name.lower()

    VINA = auto()
    PSOVINA = auto()
    QVINA = auto()
    SMINA = auto()

@dataclass(repr=True, eq=False)
class VinaCalculationData:
    """

    Attributes
    ---------
    smi : str
        the SMILES string of the ligand that will be docked
    receptor : Optional[str]
        the filepath of a receptor to prepare for docking
    software : Software
        the software that will be used
    center : Tuple[float, float, float]
        the center of the docking box
    size : Tuple[float, float, float]
        the x-, y-, and z-radii of the docking box
    ncpu : int
        the number of cpu cores to use during the docking calculation
    extra : Optional[List[str]]
        additional command line arguments that will be passed to the
        docking calculation
    name : str
        the name to use when creating the ligand input file and output files
    input_file : Optional[str]
    in_path: Union[str, Path]
        the path under which input will be placed
    out_path: Union[str, Path]
        the path under which output will be placed
    score_mode : str
        the mode used to calculate a score for an individual docking
        calculation given multiple output scored conformations
    k : int
        the number of top scores to use if calculating an average
    prepared_ligand: Optional[Union[str, Path]]
    prepared_receptor: Optional[Union[str, Path]]
    result : Optional[Mapping]
        the result of the docking calculation. None if the calculation has not
        been performed yet.

    Parmeters
    ---------
    smi : str
        the SMILES string of the ligand that will be docked
    receptor : Optional[str], default=None
        the filepath of a receptor to prepare for docking
    software : Software
        the software that will be used
    center : Tuple[float, float, float]
        the center of the docking box
    size : Tuple[float, float, float], default=(10., 10., 10.)
        the x-, y-, and z-radii of the docking box
    ncpu : int, default=1
        the number of cpu cores to use during the docking calculation
    extra : Optional[List[str]], default=None
        additional command line arguments that will be passed to the
        docking calculation
    name : str, default='ligand'
    input_file : Optional[str]
    in_path: Union[str, Path], default='.'
        the path under which input will be placed
    out_path: Union[str, Path], default='.'
        the path under which output will be placed
    score_mode : str, default='best'
        the mode used to calculate a score for an individual docking
        calculation given multiple output scored conformations
    k : int, default=1
        the number of top scores to use if calculating an average
    prepared_ligand: Optional[Union[str, Path]], default=None
    prepared_receptor: Optional[Union[str, Path]], default=None
    result : Optional[Mapping], default=None
    """
    smi: str
    receptor: str
    software: Software
    center: Tuple[float, float, float]
    size: Tuple[float, float, float] = (10., 10., 10.)
    ncpu: int = 1
    extra: Optional[str] = None
    name: str = 'ligand'
    input_file : Optional[str] = None
    in_path: Union[str, Path] = '.'
    out_path: Union[str, Path] = '.'
    score_mode : ScoreMode = ScoreMode.BEST
    k : int = 1
    prepared_ligand: Optional[Union[str, Path]] = None,
    prepared_receptor: Optional[Union[str, Path]] = None
    result : Optional[Mapping] = None

    def __post_init__(self):
        self.extra = shlex.split(self.extra) if self.extra else []
        self.in_path = Path(self.in_path)
        self.out_path = Path(self.out_path)
    
    @property
    def score(self) -> Optional[float]:
        """the docking score of this calculation
        
        Raises
        ------
        NotSimulatedError
            if this calculation has not been run yet
        """
        if self.result is None:
            raise NotSimulatedError(
                'Simulation has not been run!'
            )

        try:
            return self.result['score']
        except KeyError:
            raise InvalidResultError(
                'No key: "score" in result dictionary (self.result)!'
            )