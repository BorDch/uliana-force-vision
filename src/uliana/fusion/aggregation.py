from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import asdict,dataclass,replace

from uliana.contracts.models import PressureObservation,RepetitionInterval


@dataclass(frozen=True)
class RepetitionPressureAggregation:
    rep_id:int; start_ms:int; end_ms:int; sample_count:int; channel_count:int
    mean_total_force_n:float|None; maximum_total_force_n:float|None
    lowering_mean_force_n:float|None; rising_mean_force_n:float|None; total_impulse_ns:float|None
    mean_active_cell_count:float|None; centre_of_pressure_trajectory:list[dict]
    centre_of_pressure_displacement_cells:float|None; region_time_series:list[dict]
    mean_region_imbalance_percent:float|None; maximum_region_imbalance_percent:float|None
    imbalance_persistence_fraction:float|None; imbalance_persistence_ms:int|None
    sampling_coverage:float; missing_data_fraction:float; saturation_fraction:float
    calibration_state:str; synchronization_residuals_ms:list[float]; quality_flags:list[str]
    raw_only_features:dict|None

    def to_dict(self):return asdict(self)


def _mean(values):return sum(values)/len(values) if values else None


def aggregate_repetition_pressure(interval:RepetitionInterval,observations:list[PressureObservation],config:dict,
                                  pressure_config:dict,residuals_by_timestamp:dict[int,list[float]]|None=None)->RepetitionPressureAggregation:
    items=[item for item in observations if interval.start_ms<=item.timestamp_ms<=interval.end_ms]
    grouped=defaultdict(list)
    for item in items:grouped[item.timestamp_ms].append(item)
    expected=set(pressure_config.get("expected_channels") or {item.channel_id for item in items});rate=pressure_config.get("nominal_sampling_rate_hz")
    expected_count=((interval.end_ms-interval.start_ms)/1000*rate+1)*len(expected) if rate and expected else len(items)
    coverage=min(1,len(items)/expected_count) if expected_count else 0
    totals=[];active=[];cop=[];regions=[];raw_totals=[];calibrated_all=bool(items) and all(item.calibrated_force_n is not None and item.calibration.status=="calibrated" for item in items)
    region_map=pressure_config.get("regions") or {};required_regions="left_palm" in region_map and "right_palm" in region_map
    imbalance_samples=[]
    for timestamp,at_time in sorted(grouped.items()):
        raw_totals.append((timestamp,sum(item.raw_value for item in at_time)))
        if all(item.calibrated_force_n is not None for item in at_time):
            total=sum(item.calibrated_force_n for item in at_time);totals.append((timestamp,total));active.append(sum(item.calibrated_force_n>0 for item in at_time))
            positioned=all(item.grid_position is not None and item.grid_position.row is not None and item.grid_position.column is not None for item in at_time)
            if positioned and total>0:cop.append({"timestamp_ms":timestamp,"row":sum(item.grid_position.row*item.calibrated_force_n for item in at_time)/total,"column":sum(item.grid_position.column*item.calibrated_force_n for item in at_time)/total})
            if required_regions:
                values={item.channel_id:item.calibrated_force_n for item in at_time}
                needed=set(region_map["left_palm"]+region_map["right_palm"])
                if needed<=set(values):
                    left=sum(values[x] for x in region_map["left_palm"]);right=sum(values[x] for x in region_map["right_palm"]);combined=left+right
                    if combined>0:
                        imbalance=abs(left-right)/combined*100;regions.append({"timestamp_ms":timestamp,"left_force_n":left,"right_force_n":right,"imbalance_percent":imbalance});imbalance_samples.append((timestamp,imbalance))
    impulse=sum((bt-at)/1000*(av+bv)/2 for (at,av),(bt,bv) in zip(totals,totals[1:])) if len(totals)>1 and calibrated_all else None
    bottom=interval.bottom_ms or (interval.start_ms+interval.end_ms)//2
    lowering=[value for timestamp,value in totals if timestamp<=bottom];rising=[value for timestamp,value in totals if timestamp>=bottom]
    threshold=config["balance"]["imbalance_percent"];active_ms=0;longest=0;run=None
    for (timestamp,value),(next_timestamp,_) in zip(imbalance_samples,imbalance_samples[1:]):
        if value>threshold:active_ms+=next_timestamp-timestamp;run=timestamp if run is None else run;longest=max(longest,next_timestamp-run)
        else:run=None
    duration=max(1,interval.end_ms-interval.start_ms);persistence=active_ms/duration if imbalance_samples else None
    displacement=None
    if len(cop)>1:displacement=sum(math.hypot(b["row"]-a["row"],b["column"]-a["column"]) for a,b in zip(cop,cop[1:]))
    saturation=sum(any("saturat" in flag for flag in item.quality_flags) for item in items)/len(items) if items else 0
    states={item.calibration.status for item in items};calibration="calibrated" if states=={"calibrated"} else "unavailable" if not states else "mixed_or_invalid"
    flags=sorted({flag for item in items for flag in item.quality_flags});residuals=[]
    for timestamp in grouped:residuals.extend((residuals_by_timestamp or {}).get(timestamp,[]))
    return RepetitionPressureAggregation(interval.rep_id,interval.start_ms,interval.end_ms,len(items),len({item.channel_id for item in items}),
        _mean([v for _,v in totals]) if calibrated_all else None,max((v for _,v in totals),default=None) if calibrated_all else None,
        _mean(lowering) if calibrated_all else None,_mean(rising) if calibrated_all else None,impulse,_mean(active) if calibrated_all else None,cop if calibrated_all else [],displacement if calibrated_all else None,
        regions if calibrated_all else [],_mean([v for _,v in imbalance_samples]) if calibrated_all else None,max((v for _,v in imbalance_samples),default=None) if calibrated_all else None,
        persistence if calibrated_all else None,longest if calibrated_all else None,coverage,1-coverage,saturation,calibration,residuals,flags,
        {"label":"non_physical_raw_signal","mean_total_raw_signal":_mean([v for _,v in raw_totals]),"maximum_total_raw_signal":max((v for _,v in raw_totals),default=None)} if not calibrated_all and raw_totals else None)
