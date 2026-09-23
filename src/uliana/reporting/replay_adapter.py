from __future__ import annotations

from uliana.contracts.models import SessionResult


def replay_packets(result:SessionResult)->list[dict]:
    packets=[]
    by_rep={item.get("rep_id"):item for item in result.repetition_results}
    for interval in result.repetition_intervals:
        measurements=by_rep.get(interval.rep_id,{})
        packet={"timestamp_ms":interval.end_ms,"session_relative_timestamp_ms":interval.end_ms,
            "repetition":interval.rep_id,"viewpoint":result.detected_viewpoint.value,
            "measurements":{},"unavailable":[],"provenance":{"session_id":result.session_id,"schema_version":result.schema_version}}
        pressure=measurements.get("pressure") or {}
        if pressure.get("mean_total_force_n") is not None:packet["measurements"]["mean_total_force_n"]=pressure["mean_total_force_n"]
        else:packet["unavailable"].append("force")
        assessments=[a for a in result.assessments if a.rep_id==interval.rep_id]
        packet["assessments"]=[a.to_dict() for a in assessments]
        cue=measurements.get("primary_cue")
        if cue:packet["cue"]=cue
        packets.append(packet)
    if not packets:
        packets.append({"timestamp_ms":0,"session_relative_timestamp_ms":0,"repetition":None,"measurements":{},
            "unavailable":["repetition","force"],"cue":result.primary_cue,
            "provenance":{"session_id":result.session_id,"schema_version":result.schema_version}})
    return packets
