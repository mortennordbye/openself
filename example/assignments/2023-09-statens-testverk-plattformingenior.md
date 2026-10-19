---
schema: 1
id: 2023-09-statens-testverk-plattformingenior
type: assignment
kind: client
employment: 2021-03-fjordsky-seniorkonsulent
customer: Statens testverk
customers: []
customer_public: public
customer_alias: en statlig etat
sector: offentlig forvaltning
role: Plattformingeniør
start: 2023-09
end: ongoing
breaks: []
allocation: 100
team_size: 6
tech: [Kubernetes, Argo CD, Terraform, Azure, Azure Kubernetes Service, Prometheus, Grafana]
methods: [GitOps, Scrum]
sources: [intervju 2026-09-14]
confidence: verified
status: active
last_reviewed: 2026-09-14
---

## Hva oppdraget var

Ny intern utviklerplattform på Azure for rundt 20 utviklingsteam.

## Utfordring

Hvert team drev sin egen klynge, med ulik oppsett og ingen felles overvåking.

## Eget bidrag

- Skrev Terraform-modulene for klyngene og nettverket.
- Satte opp Argo CD med ett repo per team og felles policy.
- Laget dashbord i Grafana som teamene bruker i daglig drift.

## Resultat

Ny tjeneste i produksjon tar nå én dag i stedet for to uker (kundens egne tall).

## Teknologi i praksis

AKS med Azure CNI, Argo CD med ApplicationSets, Prometheus og Grafana.

## Brukerens ord

> «Det jeg er mest stolt av er at teamene faktisk bruker det.»

## Referanse (privat)

Kari Fiktiv, seksjonsleder plattform (kontaktinfo hos eier).

## Flagg

- ⚑ emphasis: Vil ha vekt på Argo CD-delen.
