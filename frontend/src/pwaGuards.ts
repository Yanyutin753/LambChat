export interface PwaRegistrationSupport {
  isProduction: boolean;
  hasServiceWorker: boolean;
}

export function shouldRegisterPwa({
  isProduction,
  hasServiceWorker,
}: PwaRegistrationSupport): boolean {
  return isProduction && hasServiceWorker;
}
