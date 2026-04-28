export function nameToGradient(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
    hash = hash & hash;
  }
  const hue = ((hash % 360) + 360) % 360;
  const sat1 = 30 + ((hash >> 8) & 15);
  const sat2 = 25 + ((hash >> 12) & 15);
  const light1 = 72 + ((hash >> 16) & 8);
  const light2 = 65 + ((hash >> 20) & 10);
  const hue2 = (hue + 30) % 360;
  const hue3 = (hue + 60) % 360;
  return `linear-gradient(135deg, hsl(${hue}, ${sat1}%, ${light1}%), hsl(${hue2}, ${sat2}%, ${light2}%), hsl(${hue3}, ${sat1}%, ${light1}%))`;
}

export function nameToAccentColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
    hash = hash & hash;
  }
  const hue = ((hash % 360) + 360) % 360;
  return `hsl(${hue}, 40%, 55%)`;
}
