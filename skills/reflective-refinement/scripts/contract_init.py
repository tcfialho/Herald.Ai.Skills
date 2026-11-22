#!/usr/bin/env python3
"""Suggest a goal-specific evaluation contract; never invent passing tests or baseline data."""

import argparse
import json
from pathlib import Path
import re
import sys

CATEGORIES = {
    'visual': (r'\b(visual|gr[aá]fic[oa]|apar[eê]ncia|beleza|paisagem|detalhe[s]?|render|shader|textura[s]?|pista[s]?|ingame)\b',
               'Compare actual rendered outcomes under matched viewpoints with an independent blind judge.'),
    'ux': (r'\b(usabilidade|ux|fluxo[s]?|navega[cç][aã]o|acessibilidade|acessar|experi[eê]ncia de usu[aá]rio)\b',
           'Measure task completion, errors, accessibility, recovery and subjective friction.'),
    'performance': (r'\b(lat[eê]ncia|throughput|desempenho|performance|r[aá]pid[oa]|fps|mem[oó]ria|cpu|aloca[cç][aã]o)\b',
                    'Measure complete workloads and behavior guards in paired representative regimes.'),
    'functionality': (r'\b(funcionalidade|feature|requisito|comportamento|bug|erro|corrig[ia]|regra de neg[oó]cio)\b',
                      'Verify the new behavior plus existing behavior with edge cases and negative controls.'),
    'maintainability': (r'\b(refator|arquitetura|manuten|c[oó]digo|acoplamento|modular)\b',
                        'Test a realistic future modification, retain existing behavior, and request a code-aware review.'),
    'documentation': (r'\b(documenta|manual|tutorial|readme|explica|clareza)\b',
                      'Assess whether a reader can follow the procedure correctly; keywords are not sufficient.'),
}


def infer(goal):
    text=goal.casefold()
    hits=[kind for kind,(pattern,_) in CATEGORIES.items() if re.search(pattern,text)]
    if len(hits)==1:
        return hits[0],hits
    if not hits:
        return 'mixed',[]
    return 'mixed',hits


def proposed(goal, forced=None):
    selected,hits=infer(goal)
    kind=forced or selected
    if kind not in {*CATEGORIES,'mixed'}:
        raise ValueError('unknown goal kind')
    qualitative=kind in {'visual','ux','documentation','maintainability','mixed'}
    return {'schema_version':1, 'draft':True, 'kind':kind, 'user_goal':goal,
            'primary_outcome':goal, 'case_ids':[], 'hard_checks':[],
            'benchmark':None, 'target_checks':[], 'primary_metrics':[], 'protected_paths':[],
            'reference_evidence':{},
            'review':{'required':qualitative, 'criteria':[], 'criterion_guidance':{},
                      'required_nonregression':[], 'reverse_order':kind in {'visual','ux'},
                      'calibrate':kind in {'visual','ux'}},
            'setup_notes':['Inspect actual artifact and users/states before choosing measurable outcomes.',
                           'Replace draft=true only after scenarios, baselines, guards and checks are grounded.',
                           'Use rendered evidence and blind judge for visual/UX. For code quality assess real future changes.',
                           'Freeze priority_order, target_checks and severity anchors if appropriate; KEEP is not DONE.',
                           'Check a known-bad and A=A control before trusting evaluation.'],
            'possible_kinds':hits, 'measurement_advice':CATEGORIES.get(kind, ('', 'Select relevant outcomes from actual observations.'))[1]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--goal',required=True)
    parser.add_argument('--kind',choices=[*CATEGORIES,'mixed'])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not args.goal.strip(): parser.error('goal is blank')
    if args.output.exists(): parser.error('contract exists; inspect instead of overwriting it')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(proposed(args.goal,args.kind),indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':'DRAFT_NEEDS_EVIDENCE','kind':proposed(args.goal,args.kind)['kind'],
                      'path':str(args.output)},ensure_ascii=False))
if __name__=='__main__':sys.exit(main())
