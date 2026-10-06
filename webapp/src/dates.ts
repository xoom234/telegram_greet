/** dd.mm.yyyy → yyyy-mm-dd (значение для <input type="date">). */
export function dmyToIso(dmy: string): string {
  const [d, m, y] = dmy.split(".");
  return `${y}-${m}-${d}`;
}

export function isoToDmy(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

export function shiftIso(iso: string, days: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d + days));
  return date.toISOString().slice(0, 10);
}

const WEEKDAYS = ["вс", "пн", "вт", "ср", "чт", "пт", "сб"];
const MONTHS = [
  "января", "февраля", "марта", "апреля", "мая", "июня",
  "июля", "августа", "сентября", "октября", "ноября", "декабря",
];

export function humanDate(iso: string, todayIso?: string): string {
  if (todayIso) {
    if (iso === todayIso) return "Сегодня";
    if (iso === shiftIso(todayIso, -1)) return "Вчера";
  }
  const [y, m, d] = iso.split("-").map(Number);
  const wd = WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
  return `${d} ${MONTHS[m - 1]}, ${wd}`;
}
