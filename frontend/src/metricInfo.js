// What each biomechanics finding means + a typical range for a well-coordinated delivery.
// Ranges are coaching guidance from cricket biomechanics literature (approximate, 2D video) — not medical norms.
// key: exact metric key, or base key (phase suffix _gather/_bfc/_ffc/_br stripped). range: [lo, hi] (abs if abs:true).
const I = {
  shoulder_angle_gather: { d: 'Angle between upper arm and trunk at the gather (arm loading).', r: [20, 70] },
  shoulder_angle_ffc: { d: 'Bowling arm vs trunk at front-foot contact; arm still coming up behind.', r: [30, 120] },
  shoulder_angle_br: { d: 'Bowling arm vs trunk at release; high = arm close to vertical.', r: [150, 185] },
  elbow_angle: { d: 'Bowling elbow at release; 180° = fully straight arm.', r: [165, 185] },
  release_height: { d: 'Height of the hand at release divided by body height. Higher = more bounce.', r: [1.1, 1.35] },
  wrist_offset: { d: 'How far the hand is ahead of the front ankle at release (÷ height).', r: [-0.1, 0.3] },
  front_arm_elev_ffc: { d: 'Front (non-bowling) arm height at landing; 180° = straight up. A high front arm helps rotation.', r: [110, 180] },
  front_arm_elev_br: { d: 'Front arm at release; it should have been pulled down by now.', r: [0, 80] },
  front_arm_pulldown: { d: 'How much the front arm drops from landing to release (drives trunk rotation).', r: [60, 180] },
  shoulder_tilt: { d: 'Tilt of the shoulder line in the image (0° = level). Large tilt at release is normal as the bowling shoulder rises.', r: null },
  shoulder_rot: { d: 'Shoulder rotation estimated from depth (low precision) — for reference only.', r: null },
  hip_rot: { d: 'Hip rotation estimated from depth (low precision) — for reference only.', r: null },
  arm_ang_speed: { d: 'Peak speed of the bowling arm around the shoulder near release (slow-motion clips read lower).', r: null },
  front_knee_ffc: { d: 'Front knee at landing; 180° = straight. A firm (near-straight) knee transfers energy.', r: [160, 185] },
  front_knee_br: { d: 'Front knee at release; it should stay firm or straighten.', r: [160, 190] },
  front_knee_delta: { d: 'Knee change from landing to release: + = straightening (brace), − = bending (collapse).', r: [0, 30] },
  back_knee: { d: 'Back knee at back-foot contact (load before the drive).', r: [130, 175] },
  back_knee_drive: { d: 'Maximum back-leg straightening while driving toward the target.', r: [150, 185] },
  hip_tilt: { d: 'Hip line tilt in the image (0° = level).', r: null },
  foot_align: { d: 'Front foot angle relative to the pitch line; 0° = pointing down the pitch.', r: [0, 20] },
  stride_length: { d: 'Distance between feet at front-foot contact (÷ height). Typical fast-bowler stride ≈ 0.7–0.9.', r: [0.65, 0.95] },
  foot_lateral: { d: 'Sideways offset of the front foot vs the back foot (÷ height); ~0 = in line.', r: [-0.1, 0.1], abs: false },
  trunk_lean_ffc: { d: 'Forward lean of the trunk at landing (+ = toward the batter).', r: [-10, 20] },
  trunk_lean_br: { d: 'Forward trunk flexion at release; drives momentum into the ball.', r: [15, 45] },
  trunk_lateral: { d: 'Side-bend of the trunk (away from the bowling arm). Very large values load the lower back.', r: [0, 30], abs: true },
  separation_ffc: { d: 'Angle between hip line and shoulder line at landing; stores elastic energy.', r: [30, 45], abs: true },
  separation_bfc: { d: 'Hip-shoulder angle at back-foot contact; large values suggest a mixed action.', r: [0, 20], abs: true },
  pelvic_drop: { d: 'Hip drop on landing (0° = level hips).', r: [0, 5], abs: true },
  counter_rotation: { d: 'Shoulders twisting away from the target between back- and front-foot contact.', r: [0, 20], abs: true },
  head_stability: { d: 'How much the head moves relative to the hips from back-foot contact to release (% of height).', r: [0, 5] },
  runup_momentum: { d: 'Hip speed at back-foot contact in body-heights per second (slow-motion clips read lower).', r: [1.4, 2.6] },
  com_decel: { d: 'How quickly the body slows after release (heights/s²).', r: null },
  balance_offset: { d: 'Centre of mass vs feet 0.4 s after release (÷ height); near 0 = balanced follow-through.', r: [-0.15, 0.3] },
}

const PHASES = ['_gather', '_bfc', '_ffc', '_br']
export function metricInfo(key) {
  if (I[key]) return I[key]
  for (const p of PHASES) if (key.endsWith(p) && I[key.slice(0, -p.length)]) return I[key.slice(0, -p.length)]
  return null
}

const UNIT = { deg: '°', ratio: '', pct_height: '%', height_per_s: ' ht/s', height_per_s2: ' ht/s²', deg_s: '°/s' }
export const rangeText = (info, unit) => (info?.r ? `${info.abs ? '|x| ' : ''}${info.r[0]}–${info.r[1]}${UNIT[unit] ?? ''}` : '—')

/** 'in' | 'out' | null */
export function rangeStatus(info, value) {
  if (!info?.r || value == null) return null
  const v = info.abs ? Math.abs(value) : value
  return v >= info.r[0] && v <= info.r[1] ? 'in' : 'out'
}
