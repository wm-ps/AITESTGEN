import type {
  CollectionCaseRead,
  CollectionDetail,
  CollectionSummary,
} from '../../../api'

export function summary(over: Partial<CollectionSummary> = {}): CollectionSummary {
  return { id: 'c1', name: 'Smoke', test_case_count: 2, unavailable_count: 0, run_count: 0, ...over }
}

export function testCase(
  id: string,
  name: string,
  journey: string,
  number: number,
  inCollections: { id: string; name: string }[] = [],
): CollectionCaseRead {
  return {
    scenario_id: id,
    test_case_number: number,
    name,
    journey_id: `j-${journey}`,
    journey_name: journey,
    in_collections: inCollections,
  }
}

export function detail(over: Partial<CollectionDetail> = {}): CollectionDetail {
  return {
    id: 'c1',
    name: 'Smoke',
    test_case_count: 0,
    journey_count: 0,
    run_count: 0,
    available: [],
    unavailable: [],
    recent_runs: [],
    ...over,
  }
}
