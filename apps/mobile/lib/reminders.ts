import * as Notifications from "expo-notifications";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

const K_HOUR = "ace.reminderHour";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true, shouldPlaySound: false, shouldSetBadge: false,
    shouldShowBanner: true, shouldShowList: true,
  }),
});

async function ensureChannel() {
  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("daily-quest", {
      name: "Daily quest reminder",
      importance: Notifications.AndroidImportance.DEFAULT,
    });
  }
}

export async function getReminderHour(): Promise<number | null> {
  const v = await SecureStore.getItemAsync(K_HOUR);
  return v === null ? null : Number(v);
}

/** Schedule (or move) the daily reminder. Returns false if permission was denied. */
export async function setDailyReminder(hour: number): Promise<boolean> {
  const perm = await Notifications.requestPermissionsAsync();
  if (!perm.granted) return false;
  await ensureChannel();
  await Notifications.cancelAllScheduledNotificationsAsync();
  await Notifications.scheduleNotificationAsync({
    content: {
      title: "Today's quest awaits 🎯",
      body: "Your Ace session is prepared — a focused half hour keeps the streak alive.",
    },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.DAILY,
      hour, minute: 0,
      channelId: Platform.OS === "android" ? "daily-quest" : undefined,
    } as Notifications.DailyTriggerInput,
  });
  await SecureStore.setItemAsync(K_HOUR, String(hour));
  return true;
}

export async function clearDailyReminder(): Promise<void> {
  await Notifications.cancelAllScheduledNotificationsAsync();
  await SecureStore.deleteItemAsync(K_HOUR);
}
