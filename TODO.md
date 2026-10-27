# TODO

- Add an opt-in photo-analysis workflow to assessment evidence:
  - Reuse the existing evidence upload and storage flow; persist each photo before requesting analysis so an analysis failure never loses the evidence.
  - Let the engineer add a description of what the photo shows or what to inspect, and provide relevant assessment context such as building type, checklist item, and location.
  - Implement the analysis request and result handling within the repository's specified Python/Flask toolchain. Keep credentials and image processing on the server, and do not introduce a separate JavaScript runtime or build toolchain.
  - Present an advisory structured result alongside its source photo: visual summary, components and conditions, observations with severity and confidence, potential deficiencies with severity and confidence, image limitations, and suggested follow-up checks. Allow retrying analysis without re-uploading the evidence.
  - Add an assessment-wide “Ongoing considerations” section that consolidates findings and follow-up checks from all analyzed photos, shows supporting evidence and locations, and ranks items using severity, confidence, and recurrence. Use transparent weights (severity: info 1, minor 2, moderate 4, severe 8; confidence: low 0.4, medium 0.7, high 1; recurrence multiplier capped at 1.8, increasing by 0.2 per additional supporting photo) and deduplicate matching descriptions without losing source-photo links.
  - Preserve existing checklist, evidence, and report behavior. Never automatically set checklist status or treat model output or ranking as an ASCE 41 determination; require engineer verification and clearly label results as advisory.
  - Cover authorization and assessment ownership, failed/retried analysis, repeated findings across photos, records with no analysis, and legacy evidence in tests.
  - After the main-app photo-analysis workflow has been implemented and validated, remove the temporary `/integration-staging` prototype directory.
  > **Comment:** The separate `integration-staging/photo-analysis` prototype demonstrates the desired photo description, structured review, and cumulative considerations workflow. Reimplement these behaviors in the main app using only the toolchain documented in `AGENTS.md`; do not copy its separate runtime or build setup into the application.
