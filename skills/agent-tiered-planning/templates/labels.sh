#!/bin/bash
# Label scheme for agent-tiered planning: capability tiers + effort estimates, two orthogonal axes.
#   ./labels.sh owner/repo
set -eu
REPO="${1:?usage: labels.sh owner/repo}"

# capability tiers — how much judgment the work needs (NOT how big it is)
gh label create "agent:standard" --repo "$REPO" --color 6E9BC5 \
  --description "Spec-complete, bounded, existing patterns; any competent coding agent" --force
gh label create "agent:senior" --repo "$REPO" --color D97706 \
  --description "Cross-cutting, calibration, or quality-bar work; strong agent or high effort" --force
gh label create "agent:frontier" --repo "$REPO" --color 7C3AED \
  --description "Pattern-setting or ambiguous; strongest agent plus mandatory adversarial review" --force

# effort estimates — how big (create only if the repo lacks a scheme)
gh label create "effort:XS" --repo "$REPO" --color F3F4F6 --description "Under 1 hour" --force
gh label create "effort:S"  --repo "$REPO" --color D1D5DB --description "1-3 hours" --force
gh label create "effort:M"  --repo "$REPO" --color 9CA3AF --description "Half day" --force
gh label create "effort:L"  --repo "$REPO" --color 6B7280 --description "Full day" --force
gh label create "effort:XL" --repo "$REPO" --color 374151 --description "2-3 days; candidate to split" --force
