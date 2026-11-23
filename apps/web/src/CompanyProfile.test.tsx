import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CompanyProfile from "./CompanyProfile";
import { fetchProfile, fetchVersions, saveProfile } from "./api/profile";

vi.mock("./api/profile", async (original) => ({
  ...await original<typeof import("./api/profile")>(),
  fetchProfile: vi.fn(),
  fetchVersions: vi.fn(),
  saveProfile: vi.fn(),
}));

const pending = { version: 1, availability_status: "pendiente" as const, entries: [] };
const version = { version: 1, author_id: "usuario-sintetico", created_at: "2026-11-22T00:00:00Z" };

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchProfile).mockResolvedValue(pending);
  vi.mocked(fetchVersions).mockResolvedValue([version]);
});

describe("perfil empresarial", () => {
  it("el analista consulta el historial sin controles de edición", async () => {
    render(<CompanyProfile editable={false} />);
    const history = await screen.findByRole("group", { name: "Historial" });
    fireEvent.change(within(history).getByRole("combobox", { name: "Versión" }), { target: { value: "1" } });
    expect(await screen.findByText("Autor: usuario-sintetico")).toBeVisible();
    expect(fetchProfile).toHaveBeenCalledWith(1);
    expect(screen.queryByRole("button", { name: "Editar perfil" })).not.toBeInTheDocument();
  });

  it("el administrador envía el cargo y la dedicación cero con la versión base", async () => {
    vi.mocked(saveProfile).mockResolvedValue({ ...pending, version: 2 });
    render(<CompanyProfile editable />);
    fireEvent.click(await screen.findByRole("button", { name: "Editar perfil" }));
    fireEvent.click(screen.getByRole("button", { name: "Añadir registro" }));
    fireEvent.change(screen.getByLabelText("Tipo"), { target: { value: "disponibilidad" } });
    fireEvent.change(screen.getByLabelText("Título"), { target: { value: "Turno sintético" } });
    fireEvent.change(screen.getByLabelText("Cargo"), { target: { value: "Inspector" } });
    fireEvent.change(screen.getByLabelText("Dedicación (%)"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar nueva versión" }));
    expect(saveProfile).toHaveBeenCalledWith(1, [expect.objectContaining({
      role: "Inspector", dedication_percent: "0", status: "pendiente",
    })]);
    expect(await screen.findByRole("button", { name: "Editar perfil" })).toBeVisible();
  });
});
