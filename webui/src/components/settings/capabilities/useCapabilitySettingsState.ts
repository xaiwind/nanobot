import { useState } from "react";

import {
  DEFAULT_IMAGE_GENERATION_FORM,
  imageGenerationFormFromPayload,
} from "@/components/settings/capabilities/ImageGenerationSettings";
import {
  DEFAULT_NETWORK_SAFETY_FORM,
  networkSafetyFormFromPayload,
} from "@/components/settings/capabilities/SecuritySettings";
import {
  DEFAULT_TRANSCRIPTION_FORM,
  transcriptionFormFromPayload,
} from "@/components/settings/capabilities/TranscriptionSettings";
import {
  DEFAULT_VIDEO_GENERATION_FORM,
  videoGenerationFormFromPayload,
} from "@/components/settings/capabilities/VideoGenerationSettings";
import {
  DEFAULT_WEB_SEARCH_FORM,
  webSearchFormFromPayload,
} from "@/components/settings/capabilities/WebSettings";
import type {
  ImageGenerationSettingsUpdate,
  NetworkSafetySettingsUpdate,
  SettingsPayload,
  TranscriptionSettingsUpdate,
  VideoGenerationSettingsUpdate,
  WebSearchSettingsUpdate,
} from "@/lib/types";

export function useCapabilitySettingsState(initialSettings: SettingsPayload | null) {
  const [webSearchSaving, setWebSearchSaving] = useState(false);
  const [imageGenerationSaving, setImageGenerationSaving] = useState(false);
  const [videoGenerationSaving, setVideoGenerationSaving] = useState(false);
  const [transcriptionSaving, setTranscriptionSaving] = useState(false);
  const [networkSafetySaving, setNetworkSafetySaving] = useState(false);
  const [webSearchForm, setWebSearchForm] = useState<WebSearchSettingsUpdate>(() =>
    initialSettings ? webSearchFormFromPayload(initialSettings) : DEFAULT_WEB_SEARCH_FORM,
  );
  const [imageGenerationForm, setImageGenerationForm] = useState<ImageGenerationSettingsUpdate>(
    () => initialSettings
      ? imageGenerationFormFromPayload(initialSettings)
      : DEFAULT_IMAGE_GENERATION_FORM,
  );
  const [videoGenerationForm, setVideoGenerationForm] = useState<VideoGenerationSettingsUpdate>(
    () => initialSettings
      ? videoGenerationFormFromPayload(initialSettings)
      : DEFAULT_VIDEO_GENERATION_FORM,
  );
  const [transcriptionForm, setTranscriptionForm] = useState<TranscriptionSettingsUpdate>(
    () => initialSettings ? transcriptionFormFromPayload(initialSettings) : DEFAULT_TRANSCRIPTION_FORM,
  );
  const [networkSafetyForm, setNetworkSafetyForm] = useState<NetworkSafetySettingsUpdate>(() =>
    initialSettings ? networkSafetyFormFromPayload(initialSettings) : DEFAULT_NETWORK_SAFETY_FORM,
  );
  const [webSearchKeyVisible, setWebSearchKeyVisible] = useState(false);
  const [webSearchKeyEditing, setWebSearchKeyEditing] = useState(false);

  return {
    imageGenerationForm,
    imageGenerationSaving,
    networkSafetyForm,
    networkSafetySaving,
    setImageGenerationForm,
    setImageGenerationSaving,
    setNetworkSafetyForm,
    setNetworkSafetySaving,
    setTranscriptionForm,
    setTranscriptionSaving,
    setVideoGenerationForm,
    setVideoGenerationSaving,
    setWebSearchForm,
    setWebSearchKeyEditing,
    setWebSearchKeyVisible,
    setWebSearchSaving,
    transcriptionForm,
    transcriptionSaving,
    videoGenerationForm,
    videoGenerationSaving,
    webSearchForm,
    webSearchKeyEditing,
    webSearchKeyVisible,
    webSearchSaving,
  };
}

export type CapabilitySettingsState = ReturnType<typeof useCapabilitySettingsState>;
