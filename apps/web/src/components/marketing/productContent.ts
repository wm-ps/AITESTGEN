// The Product page's capability and audience lists, kept outside Product.tsx
// so the build's prerender step (src/prerender.tsx) can reuse the same words
// for structured data and llms.txt.

import type { ComponentType } from 'react'
import { faChartLine, faClipboardCheck, faCode, faCompass, faLayerGroup, faSitemap, faWandMagicSparkles, type IconDefinition } from '@fortawesome/free-solid-svg-icons'
import { faCirclePlay } from '@fortawesome/free-regular-svg-icons'
import { ArtExecute, ArtExplore, ArtGenerate, ArtManage } from './productArt'

export const CAPABILITIES: { name: string; icon: IconDefinition; desc: string; value: string; valueDesc: string; Art: ComponentType }[] = [
  {
    name: 'Explore',
    icon: faCompass,
    desc: 'Understand your application, explore its pages and map user journeys to establish a foundation for comprehensive testing.',
    value: 'Faster Test Preparation',
    valueDesc: 'Accelerate the journey from application understanding to automated testing.',
    Art: ArtExplore,
  },
  {
    name: 'Generate',
    icon: faWandMagicSparkles,
    desc: 'Transform application insights into intelligent test scenarios and automated Playwright test cases.',
    value: 'Reduced Manual Effort',
    valueDesc: 'Minimize repetitive test creation and execution activities.',
    Art: ArtGenerate,
  },
  {
    name: 'Execute',
    icon: faCirclePlay,
    desc: 'Execute automated tests, monitor outcomes and gain visibility into test performance.',
    value: 'Better Visibility',
    valueDesc: 'Gain centralized insights into test execution and outcomes.',
    Art: ArtExecute,
  },
  {
    name: 'Manage',
    icon: faLayerGroup,
    desc: 'Centralize test suites, test cases, test data, reports and execution schedules.',
    value: 'Operational Efficiency',
    valueDesc: 'Manage testing activities through one platform.',
    Art: ArtManage,
  },
]

export const AUDIENCES: { icon: IconDefinition; title: string; desc: string }[] = [
  { icon: faClipboardCheck, title: 'QA Managers', desc: 'Better control over test coverage, execution and reporting.' },
  { icon: faCode, title: 'QA Engineers', desc: 'Less repetitive work and easier test maintenance.' },
  { icon: faSitemap, title: 'Engineering Leaders', desc: 'Improved visibility into automation and quality workflows.' },
  { icon: faChartLine, title: 'Business Leaders', desc: 'A more efficient and structured approach to software quality.' },
]
