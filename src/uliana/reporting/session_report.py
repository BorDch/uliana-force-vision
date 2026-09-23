from __future__ import annotations

from dataclasses import replace

from uliana.contracts.models import AssessmentResult,SessionResult,SynchronizationReport,ViewpointEstimate


def build_session_result(*,session_id:str,mode:str,camera_result:SessionResult|None,
                         pressure_assessments:list[AssessmentResult],pressure_aggregations:list[dict],
                         synchronization:SynchronizationReport,pressure_available:bool,
                         primary_cue:dict|None,repeated_conditions:list[str],warnings:list[str],
                         limitations:list[str],provenance:dict)->SessionResult:
    camera_assessments=list(camera_result.assessments) if camera_result else []
    assessments=camera_assessments+pressure_assessments
    technique=[a for a in assessments if a.condition!="pressure_signal_quality"]
    answered=sum(a.result!="unavailable" for a in technique);coverage=answered/len(technique) if technique else 0.0
    camera_total=len(camera_assessments);pressure_tech=[a for a in pressure_assessments if a.condition!="pressure_signal_quality"]
    camera_cov=sum(a.result!="unavailable" for a in camera_assessments)/camera_total if camera_total else 0.0
    pressure_cov=sum(a.result!="unavailable" for a in pressure_tech)/len(pressure_tech) if pressure_tech else 0.0
    sync_cov=synchronization.matched_fraction if synchronization.status=="acceptable" and synchronization.matched_fraction is not None else 0.0
    cues_by_rep={cue["rep_id"]:cue for cue in (primary_cue.get("per_repetition",[]) if primary_cue else [])}
    repetitions=[]
    for aggregation in pressure_aggregations:
        rep_id=aggregation["rep_id"];repetitions.append({"rep_id":rep_id,"pressure":aggregation,
            "assessments":[a.to_dict() for a in assessments if a.rep_id==rep_id],"primary_cue":cues_by_rep.get(rep_id)})
    unavailable=[a for a in assessments if a.result=="unavailable"]
    reason_counts={reason:sum(a.reason==reason for a in unavailable) for reason in sorted({a.reason for a in unavailable if a.reason})}
    combined_warnings=list(dict.fromkeys((camera_result.warnings if camera_result else [])+warnings))
    provenance=dict(provenance);provenance["unavailable_reason_distribution"]=reason_counts
    return SessionResult("1.0",session_id,mode,camera_result.repetition_count if camera_result else None,
        list(camera_result.repetition_intervals) if camera_result else [],camera_result.detected_viewpoint if camera_result else ViewpointEstimate("unknown",None,"camera_unavailable"),
        assessments,{"repetitions":len(pressure_aggregations)} if pressure_available else None,synchronization,coverage,
        combined_warnings,unavailable,list(camera_result.viewpoint_changes) if camera_result else [],provenance,repetitions,
        primary_cue.get("session") if primary_cue else None,repeated_conditions,
        {"camera":camera_result is not None,"pressure":pressure_available,"synchronization":synchronization.status=="acceptable"},
        {"camera":camera_cov,"pressure":pressure_cov,"synchronized":sync_cov,"assessment":coverage,
         "abstention":1-coverage if technique else 0.0},limitations)
