"""Explicit reported-cash bridges and scenario contracts, with no inferred evidence."""
from copy import deepcopy
from datetime import date
from decimal import Decimal

from planning_alignment import amount, finish, fraction
from quant_common import require, timestamp


def owner_cash_bridge(document):
    """Separate reported FCF, maintenance-only cash, SBC and supported cash addbacks."""
    start,end=date.fromisoformat(document['period_start']),date.fromisoformat(document['period_end'])
    require(start<=end and document.get('amount_unit'),'FINANCIAL_PERIOD_AND_UNIT_REQUIRED')
    for field in ('cash_adjustments','earnings_adjustments'):
        rows=document.get(field,[])
        require(isinstance(rows,list) and all(isinstance(r,dict) and isinstance(r.get('id'),str) and r['id'] for r in rows),'ADJUSTMENT_IDS_REQUIRED')
        require(len({r['id'] for r in rows})==len(rows),'DUPLICATE_ADJUSTMENT_IDS')
    cfo=amount(document['reported_cfo']);capex=amount(document['total_capex'],minimum=0)
    maintenance=amount(document['maintenance_capex'],minimum=0) if document.get('maintenance_capex') is not None else None
    growth=amount(document['growth_capex'],minimum=0) if document.get('growth_capex') is not None else None
    require(maintenance is None or maintenance<=capex,'MAINTENANCE_EXCEEDS_TOTAL_CAPEX')
    require(growth is None or growth<=capex,'GROWTH_EXCEEDS_TOTAL_CAPEX')
    split_residual=capex-maintenance-growth if maintenance is not None and growth is not None else None
    sbc=amount(document['sbc_added_back_in_cfo'],minimum=0) if document.get('sbc_added_back_in_cfo') is not None else None
    acquisition=amount(document['acquisition_cash_paid'],minimum=0) if document.get('acquisition_cash_paid') is not None else None
    wc=amount(document['working_capital_cfo_effect']) if document.get('working_capital_cfo_effect') is not None else None
    adjustments=[];supported=Decimal(0);unresolved=[]
    for row in document.get('cash_adjustments',[]):
        missing=[k for k in ('amount','reported_cfo_effect','paid_on','cash_tax_treatment','evidence') if row.get(k) is None or row.get(k)=='']
        missing += [k for k in ('cash_tax_treatment','evidence') if not row.get(k) and k not in missing]
        reason=None
        if missing:reason='CASH_TIMING_TAX_OR_CFO_EFFECT_EVIDENCE_MISSING'
        elif not start<=date.fromisoformat(row['paid_on'])<=end:reason='CASH_EFFECT_OUTSIDE_REPORTED_PERIOD'
        elif amount(row['amount']) != -amount(row['reported_cfo_effect']):reason='ADJUSTMENT_DOES_NOT_REVERSE_DECLARED_CFO_EFFECT'
        if reason:
            unresolved.append({'id':row['id'],'reason':reason,'missing':missing})
        else:
            supported+=amount(row['amount']);adjustments.append(deepcopy(row))
    earnings=[];normalized_income=None
    if document.get('reported_net_income') is not None:
        normalized_income=amount(document['reported_net_income'])
        for row in document.get('earnings_adjustments',[]):
            require(row.get('basis') in {'explicit_assumption','supported_disclosure'} and row.get('rationale'),'EARNINGS_ADJUSTMENT_BASIS_REQUIRED')
            normalized_income+=amount(row['after_tax_amount']);earnings.append(deepcopy(row))
    reported=cfo-capex
    missing_bridge=[k for k in ('maintenance_capex','growth_capex','sbc_added_back_in_cfo','acquisition_cash_paid','working_capital_cfo_effect','reported_net_income') if document.get(k) is None]
    return finish(document,'owner-cash-bridge',status='PARTIAL' if unresolved or missing_bridge or split_residual not in (None,0) else 'COMPUTED',
                  amount_unit=document['amount_unit'],measurement_period={'start':document['period_start'],'end':document['period_end']},
                  reported_cfo=cfo,total_capex=capex,reported_fcf=reported,
                  maintenance_only_cash=cfo-maintenance if maintenance is not None else None,
                  maintenance_only_definition='CFO minus supplied maintenance capex; excludes growth capex and retains CFO SBC addback.',
                  capex_split_residual=split_residual,after_total_capex_and_acquisitions=reported-acquisition if acquisition is not None else None,
                  sbc_retained_in_reported_fcf=sbc,sbc_deducted_economic_proxy=reported-sbc if sbc is not None else None,
                  pre_working_capital_cfo=cfo-wc if wc is not None else None,
                  normalized_earnings_scenario=normalized_income,earnings_adjustments=earnings,
                  supported_cash_adjustments=adjustments,unresolved_cash_adjustments=unresolved,
                  cash_after_supported_adjustments=reported+supported,
                  fcf_after_declared_cash_adjustments=None if unresolved else reported+supported,
                  declared_cash_adjustments_fully_supported=not unresolved,missing_bridge_fields=missing_bridge,
                  bridge_conservation_residual=cfo-capex-reported,
                  limitation='Earnings adjustments never transfer automatically to CFO; no owner-value judgment or addback authenticity is established.')


def acquisition_cash(document):
    """Incremental scenario cash only; a complete deal NPV needs a separate cash stream."""
    synergy=amount(document['pretax_synergies_per_year'],minimum=0);tax=fraction(document['tax_rate'])
    integration=[amount(v,minimum=0) for v in document['integration_costs_by_year']]
    interest=[amount(v,minimum=0) if v is not None else None for v in document['interest_cash_by_year']]
    years=len(integration);require(years>0 and len(interest)==years,'MATCHED_ANNUAL_CASH_PERIODS_REQUIRED')
    basis=document['integration_cash_basis'];ibasis=document['interest_cash_basis']
    allowed={'after_tax_cash','pretax_deductible','pretax_nondeductible','unknown'}
    require(basis in allowed and ibasis in allowed,'EXPLICIT_CASH_TAX_BASIS_REQUIRED')
    def after_tax(value,b):
        return None if value is None or b=='unknown' else value*(1-tax) if b=='pretax_deductible' else value
    results=[];identifiers=set()
    for scenario in document['scenarios']:
        require(scenario['id'] not in identifiers,'UNIQUE_SCENARIO_IDS');identifiers.add(scenario['id'])
        ramp=[fraction(v,'ramp') for v in scenario['ramp_fraction_by_year']]
        require(len(ramp)==years,'MATCHED_SYNERGY_PERIODS_REQUIRED')
        delay=scenario['delay_years'];require(type(delay) is int and delay>=0,'NONNEGATIVE_INTEGER_DELAY')
        realization=fraction(scenario['realization_fraction']);rows=[]
        for i in range(years):
            ramp_value=ramp[i-delay] if i>=delay else Decimal(0)
            pretax=synergy*ramp_value*realization
            integration_cash=after_tax(integration[i],basis);interest_cash=after_tax(interest[i],ibasis)
            net=pretax*(1-tax)-integration_cash-interest_cash if integration_cash is not None and interest_cash is not None else None
            rows.append({'year':i+1,'pretax_realized_synergies':pretax,'after_tax_synergies':pretax*(1-tax),
                         'integration_cash':integration_cash,'interest_cash':interest_cash,'incremental_net_cash':net})
        results.append({'id':scenario['id'],'annual_cash':rows,
                        'cumulative_incremental_cash':sum((r['incremental_net_cash'] for r in rows),Decimal(0)) if all(r['incremental_net_cash'] is not None for r in rows) else None,
                        'total_deal_npv':None})
    total_npv=None;deal_missing=[]
    deal=document.get('complete_deal_cashflow_contract')
    if deal:
        require(deal.get('cashflow_basis') in {'equity','enterprise'} and deal.get('scope_complete') is True,'COMPLETE_DEAL_BASIS_REQUIRED')
        require(deal.get('evidence_or_assumptions'),'DEAL_CASHFLOW_SCOPE_EVIDENCE_REQUIRED')
        require(deal.get('dated_year_cashflows') and
                (any(r.get('scope')=='complete_terminal_residual' for r in deal['dated_year_cashflows']) or
                 deal.get('terminal_value_assumption')=='zero_explicitly'),'EXPLICIT_COMPLETE_TERMINAL_SCOPE_REQUIRED')
        rate=amount(deal['annual_discount_rate']);require(rate>-1,'DISCOUNT_RATE_ABOVE_MINUS_ONE')
        total_npv=-amount(deal['initial_cash_outlay'],minimum=0)
        for row in deal['dated_year_cashflows']:
            year=amount(row['years_after_initial'],minimum=0)
            require(row.get('scope') in {'complete_operating_cash','complete_terminal_residual'},'COMPLETE_CASHFLOW_SCOPE_REQUIRED')
            total_npv+=amount(row['cash_amount'])/((1+rate)**year)
    else:
        deal_missing=['standalone_target_cash_flows','initial_net_acquisition_cash','residual_value_or_terminal_cash','discount_rate','consistent_financing_cashflow_basis']
    old=amount(document['existing_shares'],minimum='0.000000000001');new=amount(document['new_shares'],minimum=0)
    return finish(document,'acquisition-incremental-cash',scenarios=results,existing_shares=old,new_shares=new,
                  post_issue_shares=old+new,new_shares_fraction_of_post_issue=new/(old+new),
                  total_deal_npv=total_npv,missing_total_deal_inputs=deal_missing,
                  limitation='Interim incremental synergy cash is not total deal NPV. Delays shift synergies only; integration/financing schedules remain the explicitly supplied schedules.')


def _distribution_value(document,scenario,terminal,years):
    entry=amount(document['entry_price'],minimum='0.000000000001')
    dividend=amount(scenario['cumulative_dividends_per_share'],minimum=0)
    entry_bps=amount(document['entry_cost_bps'],minimum=0);exit_bps=amount(document['exit_cost_bps'],minimum=0)
    require(entry_bps<10000 and exit_bps<10000,'COST_BPS_RANGE')
    entry_cost=entry*entry_bps/10000;exit_cost=terminal*exit_bps/10000
    proceeds=terminal-exit_cost+dividend;outlay=entry+entry_cost
    present=None;pv_terminal=None
    if document.get('annual_discount_rate') is not None:
        discount=amount(document['annual_discount_rate']);require(discount>-1,'DISCOUNT_RATE_ABOVE_MINUS_ONE')
        pv_terminal=(terminal-exit_cost)/((1+discount)**years)
        if document.get('dividend_timing')=='terminal':present=proceeds/((1+discount)**years)
        elif isinstance(scenario.get('dividend_schedule'),list):
            require(sum((amount(r['amount_per_share'],minimum=0) for r in scenario['dividend_schedule']),Decimal(0))==dividend,'DIVIDEND_SCHEDULE_TOTAL_MISMATCH')
            present=pv_terminal
            for row in scenario['dividend_schedule']:
                when=amount(row['years_after_entry'],minimum=0);require(when<=years,'DIVIDEND_OUTSIDE_MODEL_HORIZON')
                present+=amount(row['amount_per_share'])/((1+discount)**when)
    return {'terminal_share_price':terminal,'cumulative_dividends_per_share':dividend,'entry_cost_per_share':entry_cost,
            'exit_cost_per_share':exit_cost,'entry_outlay_per_share':outlay,'net_terminal_proceeds_plus_dividends':proceeds,
            'net_total_return_fraction':proceeds/outlay-1,'discounted_terminal_proceeds_only':pv_terminal,
            'present_value_of_modeled_distributions':present}


def price_scenarios(document):
    """Supplied terminal prices at arbitrary dated horizons; no trading-calendar shift."""
    start,end=timestamp(document['entry_at']),timestamp(document['exit_at'])
    require(end>start and document['day_count']=='ACT/365F','DATED_HORIZON_ACT365F_REQUIRED')
    years=amount((end-start).total_seconds())/Decimal(365*86400)
    scenarios=document['scenarios'];require(scenarios and len({s['id'] for s in scenarios})==len(scenarios),'UNIQUE_SCENARIO_IDS')
    rows=[]
    for row in scenarios:
        terminal=amount(row['terminal_price'],minimum=0)
        value=_distribution_value(document,row,terminal,years)
        rows.append({'id':row['id'],**value})
    return finish(document,'dated-price-scenarios',scenarios=rows,measurement_period={'entry':document['entry_at'],'exit':document['exit_at']},
                  discount_year_fraction=years,day_count='ACT/365F',probability_weighted_value=None,
                  limitation='Explicit supplied prices and dividend assumptions only; no horizon conversion, return calibration or automatic terminal-price inference.')


def _terminal(document,scenario):
    years=document['years'];require(type(years) is int and years>=1,'WHOLE_MODEL_YEARS_REQUIRED')
    revenue=amount(document['starting_revenue'],minimum=0);shares=amount(document['starting_shares'],minimum='0.000000000001')
    growth=amount(scenario['annual_revenue_growth']);dilution=amount(scenario['annual_dilution'])
    require(growth>=-1 and dilution>-1,'GROWTH_DILUTION_RANGE')
    margin=fraction(scenario['terminal_ebit_margin']);tax=fraction(scenario['tax_rate'])
    multiple=amount(scenario['exit_ev_to_ebit'],minimum=0);net_debt=amount(scenario['net_debt_at_exit'])
    maintenance=fraction(document['reinvestment']['maintenance_capex_fraction_revenue'])
    expansion=fraction(document['reinvestment']['growth_capex_fraction_positive_incremental_revenue'])
    wc=fraction(document['reinvestment']['working_capital_fraction_incremental_revenue'])
    wcbasis=document['reinvestment']['working_capital_decrease_treatment']
    require(wcbasis in {'release','no_release','unknown'},'WORKING_CAPITAL_DECREASE_TREATMENT_REQUIRED')
    rows=[]
    for year in range(1,years+1):
        prior=revenue;revenue*=1+growth;increment=revenue-prior
        wc_cash=increment*wc if increment>=0 or wcbasis=='release' else Decimal(0) if wcbasis=='no_release' else None
        rows.append({'year':year,'revenue':revenue,'revenue_change':increment,'maintenance_capex':revenue*maintenance,
                     'growth_capex':max(Decimal(0),increment)*expansion,'working_capital_cash_investment':wc_cash,
                     'total_reinvestment_cash':revenue*maintenance+max(Decimal(0),increment)*expansion+wc_cash if wc_cash is not None else None})
    shares*=((1+dilution)**years);ebit=revenue*margin;ev=ebit*multiple;equity=ev-net_debt
    require(type(document['equity_value_floor_zero']) is bool,'EQUITY_FLOOR_ASSUMPTION_REQUIRED')
    terminal=max(Decimal(0),equity)/shares if document['equity_value_floor_zero'] else equity/shares
    if terminal<0:
        priced={k:None for k in ('terminal_share_price','entry_cost_per_share','exit_cost_per_share',
                'entry_outlay_per_share','net_terminal_proceeds_plus_dividends','net_total_return_fraction',
                'discounted_terminal_proceeds_only','present_value_of_modeled_distributions')}
        priced.update(cumulative_dividends_per_share=amount(scenario['cumulative_dividends_per_share'],minimum=0),
                      status='NEGATIVE_EQUITY_RESIDUAL_NO_INVESTABLE_PRICE')
    else:
        priced=_distribution_value(document,scenario,terminal,Decimal(years));priced['status']='COMPUTED'
    return {'id':scenario['id'],'terminal_revenue':revenue,'terminal_ebit':ebit,'terminal_nopat':ebit*(1-tax),
            'terminal_enterprise_value':ev,'terminal_equity_residual_before_floor':equity,'terminal_diluted_shares':shares,
            **priced,'model_years':years,'reinvestment_schedule':rows,
            'total_reinvestment_cash':sum((r['total_reinvestment_cash'] for r in rows),Decimal(0)) if all(r['total_reinvestment_cash'] is not None for r in rows) else None,
            'interim_free_cash_flow':None,
            'reinvestment_financing_reconciled':False}


def terminal_scenarios(document):
    require(document.get('amount_unit'),'AMOUNT_UNIT_REQUIRED')
    scenarios=document['scenarios'];require(scenarios and len({s['id'] for s in scenarios})==len(scenarios),'UNIQUE_SCENARIO_IDS')
    results=[_terminal(document,s) for s in scenarios];by_id={s['id']:s for s in scenarios};sensitivities=[]
    allowed={'annual_revenue_growth','terminal_ebit_margin','tax_rate','net_debt_at_exit','annual_dilution','exit_ev_to_ebit','cumulative_dividends_per_share'}
    for row in document.get('sensitivities',[]):
        require(row['base_scenario_id'] in by_id and set(row['overrides'])<=allowed and row['overrides'],'EXPLICIT_SENSITIVITY_OVERRIDES_REQUIRED')
        changed={**deepcopy(by_id[row['base_scenario_id']]),**row['overrides'],'id':row['id']}
        result=_terminal(document,changed);result['base_scenario_id']=row['base_scenario_id'];result['parameter_changes']=deepcopy(row['overrides'])
        sensitivities.append(result)
    return finish(document,'terminal-valuation-and-reinvestment',status='PARTIAL' if any(s['status']!='COMPUTED' for s in results+sensitivities) else 'COMPUTED',scenarios=results,sensitivities=sensitivities,
                  amount_unit=document['amount_unit'],scenario_probabilities=document.get('scenario_probabilities'),
                  probability_weighted_value=None,
                  limitation='Terminal share price, dividends, after-cost return and discounted value are different quantities. Reinvestment is shown separately; exogenous exit net debt is not automatically changed or proved financeable. Interim cash flow needs margin/depreciation and cash-timing assumptions.')


def corporate_action_return(document):
    """Same security, one explicit share basis and an explicitly bounded mark window."""
    start=date.fromisoformat(document['start_mark_on']);end=date.fromisoformat(document['end_mark_on'])
    requested=date.fromisoformat(document['requested_end_on']);require(start<end<=requested,'PRICE_WINDOW_ORDER')
    initial=amount(document['start_raw_price'],minimum='0.000000000001');last=amount(document['end_raw_price'],minimum=0)
    split=amount(document['new_shares_per_old'],minimum='0.000000000001')
    effective=date.fromisoformat(document['split_effective_on']);require(start<effective<=end,'SPLIT_MUST_FALL_BETWEEN_MARKS')
    distributions=Decimal(0);included=[];outside=[]
    for dividend in document['dividends']:
        ex=date.fromisoformat(dividend['ex_on']);value=amount(dividend['cash_per_share'],minimum=0)
        basis=dividend['share_basis'];require(basis in {'old_share','new_share'},'DIVIDEND_SHARE_BASIS_REQUIRED')
        cash=value if basis=='old_share' else value*split
        record={**deepcopy(dividend),'cash_per_initial_old_share':cash}
        if start<ex<=end:distributions+=cash;included.append(record)
        else:outside.append(record)
    price_return=last*split/initial-1;total=(last*split+distributions)/initial-1
    return finish(document,'split-dividend-return',price_return_fraction=price_return,total_return_to_end_mark_fraction=total,
                  total_return_through_requested_end_fraction=total if requested==end else None,
                  dividends_in_mark_window=included,dividends_outside_mark_window=outside,
                  cash_distributions_per_initial_share=distributions,
                  missing=['terminal_mark_at_requested_end'] if requested>end else [],
                  denominator='one initial old share at start_raw_price',measurement_period={'start':document['start_mark_on'],'end':document['end_mark_on']},
                  limitation='No dividend reinvestment, tax or missing terminal-price assumption; provider EPS vintages are not assigned publication dates from another security.')


def _reit_basis(group):
    fields=('amount_unit','period_start','period_end','holder_basis')
    source={} if group.get('basis') is None else group['basis']
    require(isinstance(source,dict),'REIT_BASIS_OBJECT_REQUIRED')
    result={}
    for key in fields:
        value=source.get(key)
        require(value is None or isinstance(value,str),'REIT_BASIS_TEXT_OR_NULL')
        result[key]=value if isinstance(value,str) and value.strip() and value.strip().lower()!='unknown' else None
    for key in ('period_start','period_end'):
        if result[key] is not None:date.fromisoformat(result[key])
    require(not result['period_start'] or not result['period_end'] or result['period_start']<=result['period_end'],'REIT_PERIOD_ORDER')
    return result


def _reit_compatibility(bases):
    missing=[key for key in bases[0] if any(b[key] is None for b in bases)]
    conflicts=[key for key in bases[0] if len({b[key] for b in bases if b[key] is not None})>1]
    return {'status':'INCOMPATIBLE' if conflicts else 'UNKNOWN' if missing else 'COMPATIBLE',
            'unknown_dimensions':missing,'conflicting_dimensions':conflicts,'declared_bases':deepcopy(bases)}


def _reit_components(group,key,nonnegative=False):
    rows=group.get(key)
    if rows is None:return None
    require(isinstance(rows,list),'REIT_COMPONENT_LIST_REQUIRED')
    require(all(isinstance(r,dict) and isinstance(r.get('id'),str) and r['id'].strip() for r in rows),'REIT_COMPONENT_IDS_REQUIRED')
    require(len({r['id'] for r in rows})==len(rows),'REIT_DUPLICATE_COMPONENT_IDS')
    return [{'id':r['id'],'amount':amount(r['amount'],minimum=0 if nonnegative else None) if r.get('amount') is not None else None}
            for r in rows]


def _reit_declared_arithmetic(document):
    """Private arithmetic kernel; public callers must classify source evidence."""
    groups={key:{} if document.get(key) is None else document[key] for key in ('ffo_bridge','affo_bridge','cfo','gross_capex')}
    require(all(isinstance(g,dict) for g in groups.values()),'REIT_GROUP_OBJECTS_REQUIRED')
    bases={key:_reit_basis(g) for key,g in groups.items()}
    ffo_rows=_reit_components(groups['ffo_bridge'],'components')
    adjustments=_reit_components(groups['affo_bridge'],'adjustments')
    capex_rows=_reit_components(groups['gross_capex'],'components',True)
    def total(rows,empty_allowed=False):
        return sum((r['amount'] for r in rows),Decimal(0)) if rows is not None and (rows or empty_allowed) and all(r['amount'] is not None for r in rows) else None
    ffo=total(ffo_rows);other=total(adjustments,True);capex=total(capex_rows,True)
    recurring=amount(groups['affo_bridge']['recurring_capex'],minimum=0) if groups['affo_bridge'].get('recurring_capex') is not None else None
    cfo=amount(groups['cfo']['amount']) if groups['cfo'].get('amount') is not None else None
    metrics={}
    def metric(identifier,terms,group_ids,formula,definition):
        checked=_reit_compatibility([bases[key] for key in group_ids])
        missing=[row['id'] for row in terms if row['amount'] is None]
        value=None if missing else sum((row['coefficient']*row['amount'] for row in terms),Decimal(0))
        cross=len(group_ids)>1
        primary=value if not cross or checked['status']=='COMPATIBLE' else None
        conditional=value if cross and checked['status']=='UNKNOWN' else None
        result={'id':identifier,'formula':formula,'components':terms,'value':primary,
                'conditional_same_basis_value':conditional,'basis_compatibility':checked,'definition':definition,
                'missing_components':missing,'status':'MISSING_INPUT' if missing else 'UNRESOLVED_BASIS' if cross and checked['status']!='COMPATIBLE' else 'COMPUTED'}
        if conditional is not None:result['conditional_assumption']='Amounts share the same unit, measurement period and holder basis; these unknown dimensions are not established by arithmetic.'
        metrics[identifier]=result
        return value
    def term(identifier,value,coefficient=1):return {'id':identifier,'amount':value,'coefficient':coefficient}
    metric('ffo',[term(r['id'],r['amount']) for r in ffo_rows] if ffo_rows else [term('ffo_bridge/components',None)],
           ['ffo_bridge'],'sum(signed supplied FFO components)',groups['ffo_bridge'].get('definition'))
    affo=metric('affo',[term('ffo',ffo),term('other_affo_adjustments',other),term('recurring_capex',recurring,-1)],
        ['ffo_bridge','affo_bridge'],'ffo + sum(signed issuer AFFO adjustments) - recurring_capex',groups['affo_bridge'].get('definition'))
    metric('cfo',[term('cfo',cfo)],['cfo'],'supplied CFO','Supplied operating cash flow')
    metric('gross_capex',[term(r['id'],r['amount']) for r in capex_rows] if capex_rows is not None else [term('gross_capex/components',None)],
        ['gross_capex'],'sum(supplied gross productive capex components)','Gross capex, without inferred recurring/growth allocation')
    cash=metric('cfo_after_gross_capex',[term('cfo',cfo),term('gross_capex',capex,-1)],['cfo','gross_capex'],
        'cfo - gross_capex','Cash after the declared gross capex components')
    ffo_cfo=metric('ffo_minus_cfo',[term('ffo',ffo),term('cfo',cfo,-1)],['ffo_bridge','cfo'],
        'ffo - cfo','Arithmetic difference; no itemized FFO-to-CFO causal bridge supplied by this helper')
    difference=metric('affo_minus_cfo_after_gross_capex',[
        term('ffo_minus_cfo',ffo_cfo),term('other_affo_adjustments',other),term('gross_capex',capex),term('recurring_capex',recurring,-1)],
        list(groups),'(ffo - cfo) + sum(signed issuer AFFO adjustments) + (gross_capex - recurring_capex)',
        'Arithmetic identity only; does not establish which capex components enter recurring capex')
    metrics['affo_minus_cfo_after_gross_capex']['arithmetic_identity_residual']=affo-cash-difference if all(v is not None for v in (affo,cash,difference)) else None
    mapping=document.get('recurring_capex_mapping')
    overlap={'status':'UNKNOWN','reason':'No explicit same-scope recurring-to-gross-capex mapping supplied.',
             'recurring_capex':recurring,'gross_capex_components':deepcopy(capex_rows),'allocations':None,
             'growth_or_maintenance_classification':None}
    if mapping is not None:
        overlap['declared_mapping']=deepcopy(mapping)
        try:
            require(isinstance(mapping,dict),'REIT_MAPPING_OBJECT_REQUIRED')
            require(mapping.get('recurring_is_subset_of_gross_capex') is True,'REIT_EXPLICIT_SUBSET_DECLARATION_REQUIRED')
            require(isinstance(mapping.get('evidence'),str) and mapping['evidence'].strip(),'REIT_MAPPING_EVIDENCE_REQUIRED')
            checked=_reit_compatibility([bases['affo_bridge'],bases['gross_capex'],_reit_basis(mapping)])
            overlap['basis_compatibility']=checked
            require(checked['status']=='COMPATIBLE','REIT_MAPPING_SAME_KNOWN_BASIS_REQUIRED')
            require(recurring is not None and capex_rows is not None and all(r['amount'] is not None for r in capex_rows),'REIT_MAPPING_AMOUNTS_REQUIRED')
            allocations=_reit_components(mapping,'allocations',True)
            require(allocations is not None and {r['id'] for r in allocations}=={r['id'] for r in capex_rows},'REIT_MAPPING_EXACT_COMPONENT_IDS_REQUIRED')
            require(all(r['amount'] is not None for r in allocations),'REIT_MAPPING_AMOUNTS_REQUIRED')
            caps={r['id']:r['amount'] for r in capex_rows}
            require(all(r['amount']<=caps[r['id']] for r in allocations),'REIT_MAPPING_COMPONENT_CAP_EXCEEDED')
            require(total(allocations,True)==recurring,'REIT_MAPPING_SUM_MUST_EQUAL_RECURRING_CAPEX')
            overlap.update(status='DECLARED_MAPPING_RECONCILED',reason='Arithmetic of the declared subset allocation reconciles; no source authentication or growth/maintenance classification.',
                allocations=[{'component_id':r['id'],'recurring_amount':r['amount'],
                              'not_allocated_to_recurring':caps[r['id']]-r['amount']} for r in allocations])
        except (ValueError,TypeError,KeyError) as exc:
            overlap.update(status='UNRESOLVED_MAPPING',reason=str(exc))
    fractions=[]
    property_rows=document.get('property_fractions')
    require(property_rows is None or isinstance(property_rows,list),'PROPERTY_FRACTION_LIST_REQUIRED')
    for row in property_rows or []:
        require(isinstance(row,dict) and isinstance(row.get('id'),str) and row['id'].strip(),'PROPERTY_FRACTION_ID_REQUIRED')
        value=fraction(row['value']) if row.get('value') is not None else None
        metadata={}
        for key in ('denominator','time_anchor'):
            val=row.get(key)
            require(val is None or isinstance(val,str),'PROPERTY_FRACTION_METADATA_TEXT_OR_NULL')
            metadata[key]=val if isinstance(val,str) and val.strip() and val.strip().lower()!='unknown' else None
        fractions.append({'id':row['id'],'fraction':value,**metadata,'source_record':deepcopy(row),
            'unresolved_fields':[k for k,v in metadata.items() if v is None],
            'interpretation':'No lease-count, rent, area or calendar-year denominator/anchor is inferred.'})
    require(len({r['id'] for r in fractions})==len(fractions),'DUPLICATE_PROPERTY_FRACTION_IDS')
    if document.get('distributions') is not None:
        distributions=document['distributions'];require(isinstance(distributions,dict),'REIT_DISTRIBUTIONS_OBJECT_REQUIRED')
        bases['distributions']=_reit_basis(distributions)
        paid=amount(distributions['amount'],minimum=0) if distributions.get('amount') is not None else None
        for key,denominator,scope in (('ffo',ffo,['ffo_bridge']),('affo',affo,['ffo_bridge','affo_bridge']),
                                      ('cfo_after_gross_capex',cash,['cfo','gross_capex'])):
            checked=_reit_compatibility([bases[k] for k in [*scope,'distributions']])
            ratio=paid/denominator if paid is not None and denominator is not None and denominator>0 else None
            metrics['distribution_payout_to_'+key]={'denominator_metric_id':key,'denominator':denominator,
                'distribution_amount':paid,'formula':'distributions / '+key,
                'value':ratio if checked['status']=='COMPATIBLE' else None,
                'conditional_same_basis_value':ratio if checked['status']=='UNKNOWN' else None,
                'basis_compatibility':checked,'status':'MISSING_INPUT' if paid is None or denominator is None else 'UNDEFINED_RATIO' if denominator<=0 else 'COMPUTED' if checked['status']=='COMPATIBLE' else 'UNRESOLVED_BASIS',
                'missing_components':[k for k,v in (('distributions',paid),(key,denominator)) if v is None],
                'interpretation':'Ratio to the named measure only; not distribution safety or funding verification.'}
        metric('cash_after_gross_capex_and_distributions',[term('cfo_after_gross_capex',cash),term('distributions',paid,-1)],
               ['cfo','gross_capex','distributions'],'cfo - gross_capex - distributions','Arithmetic cash residual only')
    return finish(document,'reit-cross-measure-reconciliation',
        status='PARTIAL' if overlap['status']!='DECLARED_MAPPING_RECONCILED' or any(m['status']!='COMPUTED' for m in metrics.values()) or any(r['unresolved_fields'] or r['fraction'] is None for r in fractions) else 'COMPUTED',
        metric_ledger=metrics,affo_adjustment_components=adjustments,capex_overlap=overlap,property_fractions=fractions,
        limitation='Supplied issuer bridge only, not a standardized FFO/AFFO definition. Labels or equal amounts do not establish component overlap, growth/maintenance allocation, causal cash-flow reconciliation or distribution safety. Normalization policy is unchanged.')


def reit_reconciliation(document,metadata_provenance=None):
    """Declared arithmetic only; original-record binding uses reit_sources.analyze.

    A workflow SOURCE role or supplied_observation label cannot establish that
    an accounting basis belongs to the corresponding original operand.
    """
    from reit_sources import declared
    return declared(document, metadata_provenance)
