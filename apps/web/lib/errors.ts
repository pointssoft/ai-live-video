export class ApiClientError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly requestId: string | null,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}
