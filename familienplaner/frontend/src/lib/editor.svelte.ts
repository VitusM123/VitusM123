// Zustand des Termin-Dialogs. Jede Ansicht kann ihn öffnen; gerendert wird er einmal in App.svelte.
import type { EventOccurrence } from './types';

export interface NewEventDefaults {
  start: Date;
  end: Date;
  allDay: boolean;
  memberIds: number[];
}

class EditorState {
  open = $state(false);
  occurrence = $state<EventOccurrence | null>(null);
  defaults = $state<NewEventDefaults | null>(null);
  /** Erhöht sich bei jedem Öffnen, damit das Formular neu initialisiert wird. */
  session = $state(0);

  openNew(defaults: NewEventDefaults): void {
    this.occurrence = null;
    this.defaults = defaults;
    this.session++;
    this.open = true;
  }

  openEdit(occ: EventOccurrence): void {
    this.occurrence = occ;
    this.defaults = null;
    this.session++;
    this.open = true;
  }

  close(): void {
    this.open = false;
  }
}

export const editor = new EditorState();

/** Neuer Termin am Tag ``day`` um ``hour`` Uhr (Dauer 1 h). */
export function newEventAt(day: Date, hour = 9, minute = 0, memberIds: number[] = []): NewEventDefaults {
  const start = new Date(day.getFullYear(), day.getMonth(), day.getDate(), hour, minute);
  return { start, end: new Date(start.getTime() + 3_600_000), allDay: false, memberIds };
}
