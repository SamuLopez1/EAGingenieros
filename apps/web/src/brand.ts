export const companyName = import.meta.env.VITE_COMPANY_NAME?.trim() || "EAG";
export const productName = companyName === "EAG" ? "EAG Ingenieros" : companyName;
export const simulatedMailbox = import.meta.env.VITE_SIMULATED_MAILBOX === "1";
