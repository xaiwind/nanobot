import type { Dispatch, SetStateAction } from "react";
import { useTranslation } from "react-i18next";

import { ProviderPicker, optionRowsWithCurrent } from "@/components/settings/shared/ModelControls";
import {
  NumberInput,
  ReadOnlyRow,
  RestartSettingsFooter,
  SettingsGroup,
  SettingsRow,
  SettingsSectionTitle,
} from "@/components/settings/shared/SettingsControls";
import { ToggleButton } from "@/components/settings/ToggleButton";
import type { SettingsPayload, VideoGenerationSettingsUpdate } from "@/lib/types";

// IDs verified against the Grok subscription proxy; other names return 404.
const VIDEO_MODEL_OPTIONS = ["grok-imagine-video", "grok-imagine-video-1.5"];
const VIDEO_ASPECT_RATIO_OPTIONS = ["16:9", "1:1", "9:16"];
const VIDEO_RESOLUTION_OPTIONS = ["720p", "1080p"];

export const DEFAULT_VIDEO_GENERATION_FORM: VideoGenerationSettingsUpdate = {
  enabled: false,
  model: "grok-imagine-video",
  defaultDuration: 5,
  defaultAspectRatio: "16:9",
  defaultResolution: "720p",
};

export function videoGenerationFormFromPayload(
  payload: SettingsPayload,
): VideoGenerationSettingsUpdate {
  const videoGeneration = payload.video_generation;
  if (!videoGeneration) return DEFAULT_VIDEO_GENERATION_FORM;
  return {
    enabled: videoGeneration.enabled,
    model: videoGeneration.model,
    defaultDuration: videoGeneration.default_duration,
    defaultAspectRatio: videoGeneration.default_aspect_ratio,
    defaultResolution: videoGeneration.default_resolution,
  };
}

export function VideoGenerationSettings({
  settings,
  form,
  dirty,
  saving,
  onChangeForm,
  onSave,
  onRestart,
  isRestarting,
  requiresRestartPending,
}: {
  settings: SettingsPayload;
  form: VideoGenerationSettingsUpdate;
  dirty: boolean;
  saving: boolean;
  onChangeForm: Dispatch<SetStateAction<VideoGenerationSettingsUpdate>>;
  onSave: () => void;
  onRestart?: () => void;
  isRestarting?: boolean;
  requiresRestartPending: boolean;
}) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => t(key, { defaultValue: fallback });
  const modelOptions = optionRowsWithCurrent(
    VIDEO_MODEL_OPTIONS.map((value) => ({ name: value, label: value })),
    form.model ?? "",
  );
  const aspectOptions = optionRowsWithCurrent(
    VIDEO_ASPECT_RATIO_OPTIONS.map((value) => ({ name: value, label: value })),
    form.defaultAspectRatio ?? "",
  );
  const resolutionOptions = optionRowsWithCurrent(
    VIDEO_RESOLUTION_OPTIONS.map((value) => ({ name: value, label: value })),
    form.defaultResolution ?? "",
  );

  return (
    <div className="space-y-7">
      <section>
        <SettingsSectionTitle>
          {tx("settings.sections.videoGeneration", "Video generation")}
        </SettingsSectionTitle>
        <SettingsGroup>
          <SettingsRow
            title={tx("settings.rows.videoGeneration", "Video generation")}
            description={tx(
              "settings.help.videoGeneration",
              "Runs on the xAI Grok subscription login; no API key is required.",
            )}
          >
            <ToggleButton
              checked={form.enabled ?? false}
              onChange={(enabled) => onChangeForm((prev) => ({ ...prev, enabled }))}
              ariaLabel={tx("settings.rows.videoGeneration", "Video generation")}
              label={
                form.enabled
                  ? tx("settings.values.on", "On")
                  : tx("settings.values.off", "Off")
              }
            />
          </SettingsRow>
          <SettingsRow title={tx("settings.rows.videoModel", "Video model")}>
            <ProviderPicker
              providers={modelOptions}
              value={form.model ?? ""}
              emptyLabel={tx("settings.video.selectModel", "Select video model")}
              onChange={(model) => onChangeForm((prev) => ({ ...prev, model }))}
            />
          </SettingsRow>
        </SettingsGroup>
      </section>

      <section>
        <SettingsSectionTitle>
          {tx("settings.sections.videoDefaults", "Defaults")}
        </SettingsSectionTitle>
        <SettingsGroup>
          <SettingsRow title={tx("settings.rows.defaultDuration", "Default duration (s)")}>
            <NumberInput
              value={form.defaultDuration ?? 5}
              min={1}
              max={15}
              onChange={(defaultDuration) =>
                onChangeForm((prev) => ({ ...prev, defaultDuration }))
              }
            />
          </SettingsRow>
          <SettingsRow title={tx("settings.rows.defaultAspectRatio", "Default aspect")}>
            <ProviderPicker
              providers={aspectOptions}
              value={form.defaultAspectRatio ?? ""}
              emptyLabel={tx("settings.video.selectAspect", "Select aspect")}
              onChange={(defaultAspectRatio) =>
                onChangeForm((prev) => ({ ...prev, defaultAspectRatio }))
              }
            />
          </SettingsRow>
          <SettingsRow title={tx("settings.rows.defaultResolution", "Default resolution")}>
            <ProviderPicker
              providers={resolutionOptions}
              value={form.defaultResolution ?? ""}
              emptyLabel={tx("settings.video.selectResolution", "Select resolution")}
              onChange={(defaultResolution) =>
                onChangeForm((prev) => ({ ...prev, defaultResolution }))
              }
            />
          </SettingsRow>
          <ReadOnlyRow
            title={tx("settings.rows.videoSaveDir", "Save directory")}
            value={settings.video_generation?.save_dir ?? ""}
          />
          <RestartSettingsFooter
            dirty={dirty}
            saving={saving}
            pendingRestart={requiresRestartPending}
            dirtyMessage={tx(
              "settings.status.restartAfterSaving",
              "Save changes, then restart when ready.",
            )}
            pendingMessage={tx("settings.status.savedRestartApply", "Saved. Restart when ready.")}
            onSave={onSave}
            onRestart={onRestart}
            isRestarting={isRestarting}
          />
        </SettingsGroup>
      </section>
    </div>
  );
}
