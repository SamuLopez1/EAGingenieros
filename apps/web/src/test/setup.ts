import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Sin esto, cada `render` se acumula en el mismo documento y las consultas
// encuentran elementos de pruebas anteriores. Provoca fallos por
// "Found multiple elements" y hace que los tests dependan del orden.
afterEach(() => {
  cleanup();
});
