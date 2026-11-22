// Globaler App-Zustand (Svelte-5-Runes) und Hash-Routing.
import { api } from './api';
import { applyTheme } from './theme';
import type {
  AuthStatus, CalendarInfo, DisplayState, FamilyMember, ServerEvent, ServerInfo, SyncStatus, Theme,
  UserSettings, ViewId,
} from './types';
import { connectEvents } from './ws';

const VIEWS: ViewId[] = ['month', 'week', 'family', 'activities', 'settings', 'eink'];

function viewFromHash(fallback: ViewId): ViewId {
  const name = window.location.hash.replace(/^#\/?/, '').split('?')[0] as ViewId;
  return VIEWS.includes(name) ? name : fallback;
}

class AppState {
  view = $state<ViewId>('week');
  refDate = $state(new Date());           // Bezugsdatum der Kalenderansichten
  info = $state<ServerInfo | null>(null);
  settings = $state<UserSettings | null>(null);
  theme = $state<Theme | null>(null);
  themes = $state<Theme[]>([]);
  members = $state<FamilyMember[]>([]);
  calendars = $state<CalendarInfo[]>([]);
  display = $state<DisplayState>({ screen_on: true, brightness: 100, night_active: false, hardware_backlight: false });
  sync = $state<SyncStatus | null>(null);
  auth = $state<AuthStatus>({ pin_set: false, authenticated: false });
  connected = $state(false);
  /** Wird bei jedem events.changed erhöht – Views laden daraufhin neu. */
  eventsVersion = $state(0);
  error = $state<string | null>(null);

  async init(): Promise<void> {
    try {
      const [info, settings, theme, themes, members, calendars, display, sync, auth] = await Promise.all([
        api.info(), api.settings(), api.activeTheme(), api.themes(), api.members(), api.calendars(),
        api.display(), api.syncStatus(), api.authStatus(),
      ]);
      Object.assign(this, { info, settings, themes, members, calendars, display, sync, auth });
      this.setTheme(theme);
      this.view = viewFromHash(settings.default_view);
    } catch (err) {
      this.error = `Backend nicht erreichbar: ${(err as Error).message}`;
    }
    window.addEventListener('hashchange', () => (this.view = viewFromHash(this.settings?.default_view ?? 'week')));
    connectEvents((e) => this.onServerEvent(e), (ok) => {
      const reconnected = ok && !this.connected;
      this.connected = ok;
      if (reconnected) void this.refreshAll();   // nach Verbindungsabbruch alles neu laden
    });
  }

  navigate(view: ViewId): void {
    window.location.hash = `#/${view}`;
  }

  setTheme(theme: Theme): void {
    this.theme = theme;
    applyTheme(theme);
  }

  async selectTheme(id: string): Promise<void> {
    this.settings = await api.selectTheme(id);
    this.setTheme(await api.activeTheme());
  }

  async refreshAll(): Promise<void> {
    const [settings, theme, members, calendars, display] = await Promise.all([
      api.settings(), api.activeTheme(), api.members(), api.calendars(), api.display(),
    ]);
    Object.assign(this, { settings, members, calendars, display });
    this.setTheme(theme);
    this.eventsVersion++;
  }

  private async onServerEvent(event: ServerEvent): Promise<void> {
    switch (event.type) {
      case 'events.changed':
        this.eventsVersion++;
        break;
      case 'members.changed':
        this.members = await api.members();
        break;
      case 'calendars.changed':
        this.calendars = await api.calendars();
        break;
      case 'theme.changed':
        this.setTheme(await api.activeTheme());
        break;
      case 'settings.changed':
        this.settings = await api.settings();
        break;
      case 'display.changed':
        this.display = event.payload as unknown as DisplayState;
        break;
      case 'sync.status':
        this.sync = event.payload as unknown as SyncStatus;
        break;
    }
  }

  memberById(id: number): FamilyMember | undefined {
    return this.members.find((m) => m.id === id);
  }
}

export const app = new AppState();
