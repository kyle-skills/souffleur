<skill name="souffleur-conductor-relaunch" version="1.2">

<metadata>
type: reference
parent-skill: souffleur
tier: 3
status: legacy-split
</metadata>

<sections>
- overview
- routing
- migration-note
</sections>

<section id="overview">
<context>
# Reference: Conductor Relaunch (Legacy Split)

This file previously contained the monolithic six-step relaunch sequence.
The sequence has been split into provider references plus shared wrap-up logic.

Do not implement new behavior in this file.
</context>
</section>

<section id="routing">
<mandatory>
## Recovery Routing References

Use these files instead:

1. `references/lethe-recovery-provider.md`
   - Lethe preflight, launch, completion contract, PID resolution, degraded mode
2. `references/claude-export-recovery-provider.md`
   - kill/export/size-check/relaunch fallback path
3. `references/recovery-wrap-up.md`
   - shared retry tracking and monitoring layer relaunch

All `CONTEXT_RECOVERY` handling must flow through the recovery router in `SKILL.md`.
</mandatory>
</section>

<section id="migration-note">
<guidance>
Historical examples that reference "Step 1..6 relaunch" should be interpreted as:
provider-specific relaunch steps + shared wrap-up.
</guidance>
</section>

</skill>
