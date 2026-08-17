// One code per backend subsystem so a failure on screen can be traced back
// to which pod/service is down, without guessing from free-text messages.
export type ServiceErrorCode =
  | 'API_UNAVAILABLE'
  | 'DISCOVERY_UNAVAILABLE'
  | 'GENERATION_UNAVAILABLE'
  | 'EXECUTION_UNAVAILABLE'
  | 'UNEXPECTED_ERROR'

export const SERVICE_ERROR_COPY: Record<ServiceErrorCode, { title: string; message: string }> = {
  API_UNAVAILABLE: {
    title: 'Something went wrong',
    message: "We're having trouble reaching the server. Please try again in a moment.",
  },
  DISCOVERY_UNAVAILABLE: {
    title: 'Discovery unavailable',
    message: 'The discovery service is not responding right now. Please try again in a moment.',
  },
  GENERATION_UNAVAILABLE: {
    title: 'Generation unavailable',
    message: 'The generation service is not responding right now. Please try again in a moment.',
  },
  EXECUTION_UNAVAILABLE: {
    title: 'Execution unavailable',
    message: 'The test execution service is not responding right now. Please try again in a moment.',
  },
  UNEXPECTED_ERROR: {
    title: 'Something went wrong',
    message: 'An unexpected error occurred. Please try again.',
  },
}
