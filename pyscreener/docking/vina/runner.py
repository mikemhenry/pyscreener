from itertools import takewhile
from math import ceil, log10
from pathlib import Path
import re
import subprocess as sp
import sys
from typing import List, Optional, Tuple

from openbabel import pybel
import ray

from pyscreener import utils
from pyscreener.docking.vina.data import Software, VinaCalculationData

class VinaRunner(object):
    @staticmethod
    def prepare(vinadata: VinaCalculationData) -> VinaCalculationData:
        vinadata = VinaRunner.prepare_receptor(vinadata)
        vinadata = VinaRunner.prepare_ligand(vinadata)

        return vinadata

    @staticmethod
    def prepare_receptor(
        vinadata: VinaCalculationData
    ) -> Optional[str]:
        """Prepare a receptor PDBQT file from its input file

        Parameters
        ----------
        receptor : str
            the filename of a file containing a receptor

        Returns
        -------
        receptor_pdbqt : Optional[str]
            the filepath of the resulting PDBQT file.
            None if preparation failed
        """
        receptor_pdbqt = Path(vinadata.receptor).with_suffix('.pdbqt')
        receptor_pdbqt = Path(vinadata.in_path) / receptor_pdbqt.name

        argv = [
            'prepare_receptor', '-r', vinadata.receptor, '-o', receptor_pdbqt
        ]
        try:
            sp.run(argv, stderr=sp.PIPE, check=True)
        except sp.SubprocessError:
            print(
                f'ERROR: failed to convert "{vinadata.receptor}"', 
                file=sys.stderr
            )
            return None

        vinadata.prepared_receptor = receptor_pdbqt
        return vinadata

    @staticmethod
    def prepare_from_smi(
        vinadata: VinaCalculationData
    ) -> Tuple[str, str]:
        """Prepare an input ligand file from the ligand's SMILES string

        Parameters
        ----------
        vinadata: VinaCalculationData

        Returns
        -------
        VinaCalculationData
        """
        pdbqt = Path(vinadata.in_path) / f'{vinadata.name}.pdbqt'
  
        try:
            mol = pybel.readstring(format='smi', string=vinadata.smi)
            mol.make3D()
            mol.addh()
            mol.calccharges(model='gasteiger')
        except Exception:
            pass

        mol.write(
            format='pdbqt', filename=str(pdbqt), overwrite=True, opt={'h': None}
        )

        vinadata.prepared_ligand = pdbqt
        return vinadata

    @staticmethod
    def prepare_from_file(
        filename: str, path: str = '.',  offset: int = 0
    ) -> List[Tuple[str, str]]:
        """Convert the molecules contained in the arbitrary chemical file to
        indidvidual PDBQT files with their same geometry

        Parameters
        ----------
        filename : str
            the name of the file containing the molecules
        path : str, default='.'
            the path under which the output PDBQT files should be written
        offset : int, default=0
            the numbering offset for ligand naming

        Returns
        -------
        List[Tuple[str, str]]
            a list of tuples of the SMILES string and the filepath of
            the corresponding PDBQT file
        """
        path = Path(path)

        fmt = Path(filename).suffix.strip('.')
        mols = list(pybel.readfile(fmt, filename))
        width = ceil(log10(len(mols) + offset)) + 1

        smis = []
        pdbqts = []
        for i, mol in enumerate(mols):
            if mol.title:
                name = mol.title
            else:
                name = f'ligand_{i+offset:0{width}}'
            
            smi = mol.write()
            pdbqt = str(path / f'{name}.pdbqt')
            mol.addh()
            # mol.make3D()
            mol.calccharges(model='gasteiger')
            mol.write(format='pdbqt', filename=pdbqt,
                      overwrite=True, opt={'h': None})

            smis.append(smi)
            pdbqts.append(pdbqt)

        return list(zip(smis, pdbqts))
    
    @staticmethod
    def run(vinadata: VinaCalculationData) -> Optional[List[float]]:
        """Dock the given ligand using the specified vina-type docking program 
        and parameters
        
        Returns
        -------
        scores : Optional[List[float]]
            the conformer scores parsed from the log file
        """
        p_ligand = Path(vinadata.prepared_ligand)
        ligand_name = p_ligand.stem

        name = f'{Path(vinadata.receptor).stem}_{ligand_name}'

        argv, _, log = VinaRunner.build_argv(
            ligand=vinadata.prepared_ligand,
            receptor=vinadata.prepared_receptor,
            software=vinadata.software,
            center=vinadata.center, size=vinadata.size,
            ncpu=vinadata.ncpu, extra=vinadata.extra, 
            name=name, path=Path(vinadata.out_path)
        )

        ret = sp.run(argv, stdout=sp.PIPE, stderr=sp.PIPE)
        try:
            ret.check_returncode()
        except sp.SubprocessError:
            print(
                f'ERROR: docking failed. argv: {argv}', file=sys.stderr
            )
            print(
                f'Message: {ret.stderr.decode("utf-8")}', file=sys.stderr
            )

        scores = VinaRunner.parse_log_file(log)
        if scores is None:
            score = None
        else:
            score = utils.calc_score(scores, vinadata.score_mode, vinadata.k)

        vinadata.result = {
            'smiles': vinadata.smi,
            'name': ligand_name,
            'node_id': re.sub('[:,.]', '', ray.state.current_node_id()),
            'score': score
        }

        return scores

    @staticmethod
    def build_argv(
        ligand: str, receptor: str, software: Software, 
        center: Tuple[float, float, float],
        size: Tuple[float, float, float] = (10, 10, 10),
        ncpu: int = 1, name: Optional[str] = None,
        path: Path = Path('.'), extra: Optional[List[str]] = None
    ) -> Tuple[List[str], str, str]:
        """Builds the argument vector to run a vina-type docking program

        Parameters
        ----------
        ligand : str
            the filename of the input ligand PDBQT file
        receptor : str
            the filename of the input receptor PDBQT file
        software : Software
            the docking program to run
        center : Tuple[float, float, float]
            the x-, y-, and z-coordinates of the center of the search box
        size : Tuple[float, float, float], default=(10, 10, 10)
            the  x-, y-, and z-radii, respectively, of the search box
        ncpu : int, default=1
            the number of cores to allocate to the docking program
        name : string, default=<receptor>_<ligand>)
            the base name to use for both the log and out files
        path : Path, default=Path('.')
            the path under which both the log and out files should be written
        extra : Optional[List[str]], default=None
            additional command line arguments to pass to each run

        Returns
        -------
        argv : List[str]
            the argument vector with which to run an instance of a vina-type
            docking program
        out : str
            the filepath of the out file which the docking program will write to
        log : str
            the filepath of the log file which the docking program will write to
        """
        name = name or (Path(receptor).stem+'_'+Path(ligand).stem)
        extra = extra or []

        out = path / f'{software.value}_{name}_out.pdbqt'
        log = path / f'{software.value}_{name}.log'
        
        argv = [
            software.value, f'--receptor={receptor}', f'--ligand={ligand}',
            f'--center_x={center[0]}',
            f'--center_y={center[1]}',
            f'--center_z={center[2]}',
            f'--size_x={size[0]}', f'--size_y={size[1]}', f'--size_z={size[2]}',
            f'--cpu={ncpu}', f'--out={out}', f'--log={log}', *extra
        ]

        return argv, out, log

    @staticmethod
    def parse_logfile(logfile: str) -> Optional[List[float]]:
        """parse a Vina-type log file for the scores of the conformations

        Parameters
        ----------
        logfile : str
            the path to a Vina-type log file

        Returns
        -------
        Optional[List[float]]
            the scores of the docked conformations in the ordering of the
            log file. None if no scores were parsed or the log file was 
            unparseable
        """
        TABLE_BORDER = '-----+------------+----------+----------'
        try:
            with open(logfile) as fid:
                for line in fid:
                    if TABLE_BORDER in line:
                        break

                score_lines = takewhile(
                    lambda line: 'Writing' not in line, fid
                )
        except OSError:
            pass
        
        # scores = [float(line.split()[1]) for line in score_lines]
        scores = []
        for line in score_lines:
            try:
                scores.append(float(line.split()[1]))
            except ValueError:
                continue

        return scores or None