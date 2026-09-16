export type RepStatus = "steady" | "review" | "strong";

export type DemoRep = {
  id: number;
  status: RepStatus;
  duration: string;
  depth: string;
  alignment: string;
  balance: string;
  balanceDetail: string;
  note: string;
  leftShare: number;
  rightShare: number;
  tempo: [number, number, number];
  movement: number[];
  leftSignal: number[];
  rightSignal: number[];
};

export const demoReps: DemoRep[] = [
  {
    id: 1,
    status: "steady",
    duration: "2.8 s",
    depth: "Consistent depth",
    alignment: "Stable line",
    balance: "Nearly even",
    balanceDetail: "49 / 51 relative share",
    note: "A controlled first repetition with an even lowering phase.",
    leftShare: 49,
    rightShare: 51,
    tempo: [39, 9, 52],
    movement: [86, 82, 75, 63, 47, 30, 20, 18, 20, 29, 45, 62, 76, 85],
    leftSignal: [18, 24, 35, 50, 65, 76, 81, 82, 78, 68, 52, 38, 27, 20],
    rightSignal: [20, 27, 39, 55, 69, 80, 84, 85, 81, 71, 56, 42, 31, 23],
  },
  {
    id: 2,
    status: "strong",
    duration: "2.7 s",
    depth: "Full depth",
    alignment: "Stable line",
    balance: "Even",
    balanceDetail: "50 / 50 relative share",
    note: "The clearest repetition in the set: steady line, depth and pace.",
    leftShare: 50,
    rightShare: 50,
    tempo: [38, 10, 52],
    movement: [87, 83, 76, 63, 46, 29, 17, 15, 18, 28, 44, 61, 77, 86],
    leftSignal: [18, 25, 37, 53, 68, 80, 86, 87, 83, 72, 55, 40, 28, 20],
    rightSignal: [19, 26, 38, 54, 69, 81, 85, 86, 82, 71, 54, 39, 27, 20],
  },
  {
    id: 3,
    status: "steady",
    duration: "2.9 s",
    depth: "Consistent depth",
    alignment: "Small hip shift",
    balance: "Nearly even",
    balanceDetail: "48 / 52 relative share",
    note: "A small hip shift appears near the bottom, then resolves on the return.",
    leftShare: 48,
    rightShare: 52,
    tempo: [40, 11, 49],
    movement: [87, 84, 77, 65, 50, 34, 23, 20, 23, 32, 47, 63, 77, 85],
    leftSignal: [17, 23, 34, 48, 62, 73, 78, 79, 75, 65, 50, 37, 26, 19],
    rightSignal: [21, 29, 42, 58, 72, 82, 87, 88, 84, 74, 59, 44, 32, 24],
  },
  {
    id: 4,
    status: "review",
    duration: "2.5 s",
    depth: "Slightly shorter",
    alignment: "Early return",
    balance: "Right-leaning",
    balanceDetail: "45 / 55 relative share",
    note: "Worth replaying: the return starts earlier and the right-hand signal rises first.",
    leftShare: 45,
    rightShare: 55,
    tempo: [36, 6, 58],
    movement: [86, 81, 72, 60, 48, 38, 32, 31, 34, 43, 56, 70, 81, 87],
    leftSignal: [17, 22, 31, 43, 56, 66, 71, 72, 68, 58, 45, 34, 25, 19],
    rightSignal: [23, 32, 47, 63, 78, 88, 92, 93, 88, 76, 60, 45, 33, 25],
  },
  {
    id: 5,
    status: "steady",
    duration: "2.8 s",
    depth: "Consistent depth",
    alignment: "Stable line",
    balance: "Nearly even",
    balanceDetail: "49 / 51 relative share",
    note: "Pace and alignment return to the pattern established at the start.",
    leftShare: 49,
    rightShare: 51,
    tempo: [39, 9, 52],
    movement: [87, 83, 75, 62, 46, 31, 21, 19, 22, 31, 46, 62, 77, 86],
    leftSignal: [18, 25, 36, 51, 66, 77, 82, 83, 79, 69, 53, 39, 28, 20],
    rightSignal: [20, 27, 39, 54, 69, 80, 84, 85, 81, 71, 56, 41, 30, 22],
  },
  {
    id: 6,
    status: "review",
    duration: "2.4 s",
    depth: "Reduced depth",
    alignment: "Faster return",
    balance: "Right-leaning",
    balanceDetail: "44 / 56 relative share",
    note: "The shortest repetition in the set, with a faster return and stronger right signal.",
    leftShare: 44,
    rightShare: 56,
    tempo: [34, 5, 61],
    movement: [86, 80, 70, 59, 49, 41, 37, 38, 43, 52, 64, 75, 83, 87],
    leftSignal: [16, 21, 29, 40, 51, 60, 65, 66, 62, 54, 43, 33, 24, 18],
    rightSignal: [24, 34, 49, 65, 79, 88, 92, 91, 84, 72, 58, 44, 33, 25],
  },
];

export const setSummary = {
  reps: demoReps.length,
  pace: "Mostly controlled",
  movement: "4 consistent · 2 to review",
  load: "Slight right-side tendency",
};
