from __future__ import annotations
import math
from typing import Any


def poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def score_matrix(lambda_home: float, lambda_away: float, rho: float = -0.05, max_goals: int = 12):
    """Independent Poisson score grid with Dixon-Coles low-score adjustment.

    This is a transparent baseline model, not a calibrated prediction by itself.
    Inputs must be estimated from historical data and validated out of sample.
    """
    lh, la = max(.05, min(6.0, lambda_home)), max(.05, min(6.0, lambda_away))
    matrix=[]; total=0.0
    for h in range(max_goals+1):
        row=[]
        for a in range(max_goals+1):
            p=poisson_pmf(h,lh)*poisson_pmf(a,la)
            tau=1.0
            if h==0 and a==0: tau=1-lh*la*rho
            elif h==0 and a==1: tau=1+lh*rho
            elif h==1 and a==0: tau=1+la*rho
            elif h==1 and a==1: tau=1-rho
            p=max(0.0,p*tau); row.append(p); total+=p
        matrix.append(row)
    if total <= 0: raise ValueError('Invalid score matrix normalization')
    return [[p/total for p in row] for row in matrix]


def probabilities(matrix: list[list[float]]) -> dict[str, Any]:
    out: dict[str,Any]={'home_win':0.0,'draw':0.0,'away_win':0.0,'btts_yes':0.0,'btts_no':0.0}
    lines=(0.5,1.5,2.5,3.5,4.5,5.5)
    for line in lines:
        k=str(line).replace('.','_'); out[f'over_{k}']=0.0; out[f'under_{k}']=0.0
    for team in ('home','away'):
        for line in (0.5,1.5,2.5,3.5):
            k=str(line).replace('.','_'); out[f'{team}_over_{k}']=0.0; out[f'{team}_under_{k}']=0.0
    top=(0.0,0,0)
    for h,row in enumerate(matrix):
        for a,p in enumerate(row):
            if h>a: out['home_win']+=p
            elif h==a: out['draw']+=p
            else: out['away_win']+=p
            if h>0 and a>0: out['btts_yes']+=p
            else: out['btts_no']+=p
            t=h+a
            for line in lines:
                k=str(line).replace('.','_')
                if t>line: out[f'over_{k}']+=p
                else: out[f'under_{k}']+=p
            for team,g in (('home',h),('away',a)):
                for line in (0.5,1.5,2.5,3.5):
                    k=str(line).replace('.','_')
                    if g>line: out[f'{team}_over_{k}']+=p
                    else: out[f'{team}_under_{k}']+=p
            if p>top[0]: top=(p,h,a)
    out['top_score']=[top[1],top[2]]
    return out


def no_vig_probabilities(odds: list[float]) -> list[float] | None:
    if len(odds)<2 or any(o is None or not math.isfinite(o) or o<=1 for o in odds): return None
    raw=[1.0/o for o in odds]; total=sum(raw)
    return [x/total for x in raw] if total else None


def evaluate_market(name: str, selection: str, model_p: float | None, odds: float | None,
                    market_p: float | None=None, min_ev_pct: float=2.0, bookmaker: str|None=None) -> dict[str,Any]:
    base={'market':name,'selection':selection,'bookmaker':bookmaker,'model_probability':model_p,'odds':odds,
          'fair_odds':None,'market_probability':market_p,'ev_pct':None,'status':'NOT_EVALUABLE'}
    if model_p is None or odds is None or not (0<model_p<1) or odds<=1 or not math.isfinite(odds): return base
    ev=(model_p*odds-1)*100
    base.update({'model_probability':round(model_p,6),'odds':round(odds,4),'fair_odds':round(1/model_p,4),
                 'market_probability':round(market_p,6) if market_p is not None else None,
                 'ev_pct':round(ev,3),'status':'POSITIVE_EV_CANDIDATE' if ev>=min_ev_pct else ('LOW_EDGE' if ev>0 else 'NO_VALUE')})
    return base


def analyze_quotes(lambda_home: float, lambda_away: float, quotes: list[dict], min_ev_pct: float=2.0):
    matrix=score_matrix(lambda_home,lambda_away); probs=probabilities(matrix)
    groups={}
    for q in quotes:
        if q.get('odds') and q.get('odds')>1:
            groups.setdefault(q.get('group') or q.get('market_key') or '__ungrouped__',[]).append(q)
    market_p={}
    for group in groups.values():
        # Only calculate no-vig when every quote in the explicitly-defined outcome group is present.
        nv=no_vig_probabilities([float(q['odds']) for q in group])
        if nv and len(group)>=2:
            for q,p in zip(group,nv): market_p[(q.get('selection_key'),q.get('bookmaker'))]=p
    results=[]
    for q in quotes:
        key=(q.get('selection_key'),q.get('bookmaker'))
        results.append(evaluate_market(q.get('market','Unknown'),q.get('selection',''),probs.get(q.get('model_key')),
            float(q['odds']) if q.get('odds') else None,market_p.get(key),min_ev_pct,q.get('bookmaker')))
    evaluated=[x for x in results if x['model_probability'] is not None and x['odds'] and x['ev_pct'] is not None]
    highest=max(evaluated,key=lambda x:x['model_probability'],default=None)
    value=max((x for x in evaluated if x['ev_pct']>=min_ev_pct),key=lambda x:x['ev_pct'],default=None)
    balance=max((x for x in evaluated if x['ev_pct']>0),key=lambda x:(x['model_probability']*x['ev_pct']),default=None)
    return {'expected_goals':{'home':round(lambda_home,3),'away':round(lambda_away,3)},'probabilities':probs,
      'markets':sorted(results,key=lambda x:(x['ev_pct'] is not None,x['ev_pct'] or -999),reverse=True),
      'recommendations':{'highest_probability':highest,'best_value':value,'best_balance':balance},
      'warning':'Olasılıklar model tahminidir; garanti değildir. Model kalibrasyonu ve geçmiş test yapılmadan bahis önerisi kesin güvenilir sayılmaz.'}
