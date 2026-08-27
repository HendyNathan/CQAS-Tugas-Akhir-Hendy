// Central unit conversion utilities that mirror backend/units.py

export const UNIT_LABELS = {
  mm: "mm", cm: "cm",
  MPa: "MPa", "N/mm2": "N/mm²", "kgf/cm2": "kgf/cm²", "kg/cm2": "kgf/cm²", psi: "psi",
  kN: "kN", N: "N",
  mm2: "mm²", cm2: "cm²",
  kg: "kg", g: "g",
};

const FACTORS = {
  "mm->cm": 0.1, "cm->mm": 10,
  "MPa->N/mm2": 1, "N/mm2->MPa": 1,
  "MPa->kgf/cm2": 10.19716213, "kgf/cm2->MPa": 1 / 10.19716213,
  "MPa->psi": 145.037738, "psi->MPa": 1 / 145.037738,
  "N/mm2->kgf/cm2": 10.19716213, "kgf/cm2->N/mm2": 1 / 10.19716213,
  "mm2->cm2": 0.01, "cm2->mm2": 100,
  "kN->N": 1000, "N->kN": 0.001,
  "kg->g": 1000, "g->kg": 0.001,
};

export function convert(value, source, target) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  if (!source || source === target) return number;
  const factor = FACTORS[`${source}->${target}`];
  return factor === undefined ? number : Math.round(number * factor * 1000) / 1000;
}

export function display(value, canonical, preferred) {
  if (value === null || value === undefined || value === "") return { value: null, unit: preferred || canonical };
  const target = preferred || canonical;
  return { value: convert(value, canonical, target), unit: target };
}

export function formatWithUnit(value, canonical, preferred) {
  const { value: converted, unit } = display(value, canonical, preferred);
  if (converted === null) return "—";
  return `${converted} ${UNIT_LABELS[unit] || unit}`;
}
