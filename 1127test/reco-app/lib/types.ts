export const CATEGORIES = ["채소", "과일", "정육", "수산", "곡물", "가공"] as const;
export const HOUSEHOLDS = ["1인", "2~3인", "4인+"] as const;
export const BUDGETS = [5000, 10000, 30000] as const;
export const COOKINGS = ["간편", "요리"] as const;

export type Category = (typeof CATEGORIES)[number];
export type Household = (typeof HOUSEHOLDS)[number];
export type Cooking = (typeof COOKINGS)[number];

export type Product = {
  id: number;
  name: string;
  category: Category;
  tags: string[];
  portion: Household;
  price: number;
  stock: number;
};

export type SurveyInput = {
  household: Household;
  categories: Category[];
  budget: number;
  cooking: Cooking;
  note: string | null;
};

export type Recommendation = {
  product: Product;
  score: number;
  reason: string;
  reasonSource: "ai" | "fallback";
};
