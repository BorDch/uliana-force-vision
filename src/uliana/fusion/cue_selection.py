from __future__ import annotations

from uliana.contracts.models import AssessmentResult

CUES={"body_alignment_deviation":"Keep the body line stable.","push_up_depth_proxy":"Increase the measured movement range.","left_right_pressure_balance":"Check how the load is distributed between your hands."}


def select_primary_cues(assessments:list[AssessmentResult],config:dict)->tuple[dict[int,dict],list[str]]:
    by_rep={};warnings=[];last_shown={}
    for item in assessments:by_rep.setdefault(item.rep_id,[]).append(item)
    output={}
    for rep_id in sorted(key for key in by_rep if key is not None):
        rows=by_rep[rep_id]
        for condition in config["cue_priority"]:
            matches=[item for item in rows if item.condition==condition]
            if any(item.result=="adequate" for item in matches) and any(item.result=="condition_detected" for item in matches):
                warnings.append(f"conflicting_evidence:{condition}:rep_{rep_id}");continue
            eligible=[item for item in matches if item.result=="condition_detected" and (item.confidence or 0)>=config["cue_minimum_confidence"]]
            if not eligible:continue
            if rep_id-last_shown.get(condition,-10_000)<=config["cue_repeat_cooldown_repetitions"]:continue
            chosen=max(eligible,key=lambda item:item.confidence or 0);output[rep_id]={"condition":condition,"text":CUES[condition],"confidence":chosen.confidence,"rep_id":rep_id};last_shown[condition]=rep_id;break
    return output,warnings
