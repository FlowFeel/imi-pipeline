"""phosphene-imi — IMI publish and distribute pipeline.

Status: COMPLETE — production-ready as of 2026-06-24.

This package implements the automation layer for the Independent Media
Institute's content publishing pipeline. A finished intellectual work
— arriving as an Asana task or Telegram message — moves through the
pipeline and arrives on observatory.wiki as a published, SEO-compliant
article, recorded in Salesforce, with the author notified.

The SyndicationSagaWorkflow orchestrates three outlets as a Temporal
workflow with LIFO compensation:
  - WordPress (independentmediainstitute.org)
  - Observatory MediaWiki (observatory.wiki)
  - Salesforce (Content_Management__c) + Pardot/Account Engagement

The pipeline is a TaskFlow manifest. Each step has a contract.
Business logic lives in the modules. Behave features prove the contracts.
99 tests green. Deploy-ready.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations
