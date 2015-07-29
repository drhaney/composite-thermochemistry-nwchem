# -*- coding:utf-8 mode:python; tab-width:4; indent-tabs-mode:nil; py-indent-offset:4 -*-
import sys
import argparse
import os
import shutil
import subprocess
import shlex

tpl = """start {startname}

memory {memory} mb
title {jobname}

geometry units angstroms print xyz
 load {structure}
end

python noprint
import os
import sys
sys.path.append(os.getcwd())
{composite}
end

task python
"""

class Runner(object):
    models = ["g3mp2-ccsdt", "g3mp2-qcisdt", "g4mp2", "gn-g4mp2"]
    def __init__(self, model, geofile, charge, multiplicity, nproc, memory,
                 tmpdir, verbose):
        self.model = model
        self.geofile = geofile
        self.charge = charge
        self.multiplicity = self.get_multiplicity(multiplicity)
        self.nproc = nproc or self.get_nproc()
        self.memory = memory or self.get_memory()
        self.verbose = verbose
        self.tmpdir = tmpdir

    def get_multiplicity(self, mult):
        """Validate or translate multiplicity.
        """

        m = mult.lower()
        multiplets = ["(null)", "singlet", "doublet",
                      "triplet", "quartet", "quintet",
                      "hextet", "septet", "octet"]
        if m in multiplets:
            result = m
        else:
            try:
                result = multiplets[int(m)]
            except:
                raise ValueError("Invalid multiplicity {0}".format(repr(m)))

        return result

    def get_deck(self):
        """Create a complete job deck for execution. Also return data needed
        to set up job execution.
        """

        memory_per_core = self.memory / self.nproc
        startname = os.path.basename(self.geofile).split(".xyz")[0]
        jobname = "{}_{}".format(startname, self.model)

        if self.model == "g3mp2-ccsdt":
            pymodel = "g3mp2.py"
            m = """import g3mp2
g3mp2.G3MP2(charge={charge}, mult={mult})""".format(charge=self.charge, mult=repr(self.multiplicity))
            deck = tpl.format(startname=startname, memory=memory_per_core,
                              jobname=jobname, structure=self.geofile,
                              composite=m)

        return {"deck" : deck, "pymodel" : pymodel, "geometry" : self.geofile}

    def run(self, jobdata):
        """Run NWChem for a given deck.
        """

        t = os.path.basename(self.geofile).split(".xyz")[0] + "_" + self.model
        tmpdir = self.tmpdir + t
        if not os.path.exists(tmpdir):
            os.makedirs(tmpdir)

        deckfile = t + ".nw"
        logfile = deckfile[:-3] + ".log"
        
        with open(tmpdir + "/" + deckfile, "w") as outfile:
            outfile.write(jobdata["deck"])

        shutil.copy(jobdata["pymodel"], tmpdir)
        shutil.copy(jobdata["geometry"], tmpdir)

        if self.verbose:
            redirector = "| tee "
        else:
            redirector = "&> "

        if self.nproc == 1:
            runner = "cd {0} && nwchem {1} {2} {3}".format(tmpdir, deckfile, redirector, logfile)
        else:
            runner = "cd {0} && mpirun -np {1} nwchem {2} {3} {4}".format(tmpdir, self.nproc, deckfile, redirector, logfile)

        print(runner)

        if not self.verbose:
            cmd = shlex.split(runner)
            command = ["/bin/bash", "-i", "-c"] + [" ".join(cmd)]
            p = subprocess.Popen(command, stdout=subprocess.PIPE,
                                 stdin=subprocess.PIPE)
            output = p.communicate()[0]

        else:
            os.system(runner)

    def get_memory(self):
        """Automatically get available memory (Linux only)
        """

        megabytes = 0
        
        try:
            with open("/proc/meminfo") as infile:
                data = infile.read()
            for line in data.split("\n"):
                if "MemTotal" in line:
                    kilobytes = int(line.strip().split()[1])
                    megabytes = kilobytes / 1024
        except IOError:
            megabytes = 1000

        return max(megabytes, 1000)

    def get_nproc(self):
        """Automatically get number of processors (Linux only)
        """

        nproc = 0
        amd = True

        try:
            with open("/proc/cpuinfo") as infile:
                data = infile.read()
            for line in data.split("\n"):
                if "GenuineIntel" in line:
                    amd = False
                elif "processor" in line:
                    try:
                        nproc = int(line.strip().split()[-1]) + 1
                    except ValueError:
                        pass
            #assume hyperthreading if intel processor, use only real cores
            if not amd:
                nproc /= 2
        #can't read cpuinfo, so default to 1
        except IOError:
            nproc = 1

        return max(1, nproc)

def main(args):
    try:
        m = Runner(args.model, args.xyz, args.charge, args.multiplicity,
                   args.nproc, args.memory, args.tmpdir, args.verbose)
        deck = m.get_deck()
    except:
        return True

    m.run(deck)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter, description="Treat a chemical system with one of the following composite thermochemical models: " + ", ".join(Runner.models) + ". An .xyz file or appropriate .csv file is required as input.")
    parser.add_argument("-n", "--nproc", help="Number of processor cores to use (auto-assigned if not chosen)", type=int,default=0)
    parser.add_argument("-m", "--memory", help="Maximum memory to use, in megabytes (auto-assigned if not chosen)", default=0)
    parser.add_argument("--multiplicity", help="System spin multiplicity", default="singlet")
    parser.add_argument("--model", help="Thermochemical model to use", default="g3mp2-ccsdt")
    parser.add_argument("-c", "--charge", help="System charge", type=int, default=0)
    parser.add_argument("-g", "--xyz", help="XYZ geometry file", default="")
    parser.add_argument("-v", "--verbose", help="If active, show job output as it executes", action="store_true", default=False)
    parser.add_argument("--tmpdir", help="Temporary directory", default="/tmp/")
    args = parser.parse_args()
    error = main(args)
    if error:
        parser.print_help()
