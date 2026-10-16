export function cantidad(n: number, singular: string, plural: string): string {
  return `${n} ${n === 1 ? singular : plural}`;
}
