# Example mock applications

These JSON files mimic the fields of a TTB application (Form 5100.31) for the
sample "OLD TOM DISTILLERY" bourbon label. Paste one into the optional
"compare against an application" panel on the upload page to see the match check.

- `application_match.json` - all fields agree with the sample label. It also
  demonstrates the field-specific matching: the brand matches despite different
  capitalization, and the alcohol content and net contents match on value
  ("45% Alc/Vol" vs the label's "45% Alc./Vol. (90 Proof)", "750ml" vs "750 mL").
- `application_mismatch.json` - identical except the alcohol content is 40%
  instead of 45%. This shows the tool catching a transcription error between the
  application and the label, which is exactly the routine "data entry
  verification" the agents do today.

The match check is separate from the compliance check: "Label vs Application"
(does the label match the filed form) versus "Label vs Law" (does the label
satisfy the regulations).
