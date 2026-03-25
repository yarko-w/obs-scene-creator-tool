using System.Text.Json.Nodes;

namespace OBSSceneGenerator.Services;

public record PresetConfig(string Name, int Position);

/// <summary>
/// Builds the OBS scene collection JSON structure — a direct C# port of the Python build_obs_json function.
/// </summary>
public static class ObsJsonBuilder
{
    // OBS uses this fixed UUID as the default canvas identifier
    private const string DefaultCanvasUuid = "6c69626f-6273-4c00-9d88-c5136d61696e";
    private const string StingerPath = @"C:\Program Files (x86)\KH Switcher\Stingers\Stinger120 Quick.mov";
    private const string VideoDevice = "PTZ Camera";

    public static JsonObject Build(
        string collectionName,
        string cameraIp,
        IEnumerable<PresetConfig> presets,
        bool includeMedia,
        bool includeBlack,
        string transition)
    {
        var sources = new JsonArray();
        var sceneOrder = new JsonArray();

        // ── Display Capture source + Media scene (optional) ──────────────────
        if (includeMedia)
        {
            sceneOrder.Add(new JsonObject { ["name"] = "Media" });

            var displayUuid = NewUuid();
            var displaySource = MakeSourceBase("Display Capture", "monitor_capture", "monitor_capture",
                new JsonObject { ["monitor"] = 0 },
                new JsonObject
                {
                    ["hotkeys"] = new JsonObject
                    {
                        ["libobs.mute"] = new JsonArray(), ["libobs.unmute"] = new JsonArray(),
                        ["libobs.push-to-mute"] = new JsonArray(), ["libobs.push-to-talk"] = new JsonArray()
                    }
                });
            displaySource["uuid"] = displayUuid;
            sources.Add(displaySource);

            var mediaItems = new JsonArray { MakeSceneItem("Display Capture", displayUuid, 1) };
            sources.Add(MakeSceneSource("Media", mediaItems, idCounter: 1));
        }

        // ── Video Capture source (shared across all camera preset scenes) ─────
        var videoUuid = NewUuid();
        var videoSource = MakeSourceBase(VideoDevice, "av_capture_input", "av_capture_input_v2",
            new JsonObject { ["device_name"] = VideoDevice },
            new JsonObject
            {
                ["hotkeys"] = new JsonObject
                {
                    ["libobs.mute"] = new JsonArray(), ["libobs.unmute"] = new JsonArray(),
                    ["libobs.push-to-mute"] = new JsonArray(), ["libobs.push-to-talk"] = new JsonArray()
                }
            });
        videoSource["uuid"] = videoUuid;
        sources.Add(videoSource);

        // ── Browser sources + Camera Preset scenes ───────────────────────────
        foreach (var preset in presets)
        {
            var url = $"http://{cameraIp}/cgi-bin/ptzctrl.cgi?ptzcmd&poscall&{preset.Position}";

            var browserUuid = NewUuid();
            var browserSource = MakeSourceBase(
                $"PTZ Preset \u2013 {preset.Name}",
                "browser_source", "browser_source",
                new JsonObject
                {
                    ["url"] = url,
                    ["width"] = 1920,
                    ["height"] = 1080,
                    ["restart_when_active"] = true,
                    ["shutdown"] = true
                },
                new JsonObject
                {
                    ["hotkeys"] = new JsonObject
                    {
                        ["libobs.mute"] = new JsonArray(), ["libobs.unmute"] = new JsonArray(),
                        ["libobs.push-to-mute"] = new JsonArray(), ["libobs.push-to-talk"] = new JsonArray(),
                        ["ObsBrowser.Refresh"] = new JsonArray()
                    }
                });
            browserSource["uuid"] = browserUuid;
            sources.Add(browserSource);

            // Item 1 (bottom) = browser source, hidden
            // Item 2 (top)    = video capture, visible
            var sceneItems = new JsonArray
            {
                MakeSceneItem($"PTZ Preset \u2013 {preset.Name}", browserUuid, itemId: 1, visible: false),
                MakeSceneItem(VideoDevice, videoUuid, itemId: 2, visible: true)
            };

            var presetScene = MakeSceneSource(preset.Name, sceneItems, idCounter: 2);
            var hotkeys = presetScene["hotkeys"]!.AsObject();
            hotkeys["libobs.show_scene_item.1"] = new JsonArray();
            hotkeys["libobs.hide_scene_item.1"] = new JsonArray();
            hotkeys["libobs.show_scene_item.2"] = new JsonArray();
            hotkeys["libobs.hide_scene_item.2"] = new JsonArray();
            sources.Add(presetScene);

            sceneOrder.Add(new JsonObject { ["name"] = preset.Name });
        }

        // ── Optional Black scene (empty — used for fading to black) ──────────
        if (includeBlack)
        {
            sources.Add(MakeSceneSource("Black", new JsonArray(), idCounter: 0));
            sceneOrder.Add(new JsonObject { ["name"] = "Black" });
        }

        // ── Transitions ──────────────────────────────────────────────────────
        var transitionDefs = new Dictionary<string, JsonObject>
        {
            ["Stinger"] = new JsonObject
            {
                ["name"] = "Stinger",
                ["id"] = "obs_stinger_transition",
                ["settings"] = new JsonObject
                {
                    ["transition_point_type"] = 0,   // 0 = time-based
                    ["transition_point"] = 800,       // 800ms
                    ["path"] = StingerPath
                }
            },
            ["Fade"] = new JsonObject { ["name"] = "Fade", ["id"] = "fade_transition", ["settings"] = new JsonObject() },
            ["Cut"]  = new JsonObject { ["name"] = "Cut",  ["id"] = "cut_transition",  ["settings"] = new JsonObject() }
        };

        var transitions = new JsonArray
        {
            transitionDefs.TryGetValue(transition, out var td) ? td : transitionDefs["Stinger"]
        };

        var firstScene = sceneOrder.Count > 0 ? sceneOrder[0]!["name"]!.ToString() : "Media";

        return new JsonObject
        {
            ["current_scene"]         = firstScene,
            ["current_program_scene"] = firstScene,
            ["scene_order"]           = sceneOrder,
            ["name"]                  = collectionName,
            ["groups"]                = new JsonArray(),
            ["quick_transitions"] = new JsonArray
            {
                new JsonObject { ["name"] = "Cut",  ["duration"] = 300, ["hotkeys"] = new JsonArray(), ["id"] = 1, ["fade_to_black"] = false },
                new JsonObject { ["name"] = "Fade", ["duration"] = 300, ["hotkeys"] = new JsonArray(), ["id"] = 2, ["fade_to_black"] = false },
                new JsonObject { ["name"] = "Fade", ["duration"] = 300, ["hotkeys"] = new JsonArray(), ["id"] = 3, ["fade_to_black"] = true  }
            },
            ["transitions"]        = transitions,
            ["saved_projectors"]   = new JsonArray(),
            ["canvases"]           = new JsonArray(),
            ["current_transition"] = transition,
            ["transition_duration"] = 300,
            ["preview_locked"]     = false,
            ["scaling_enabled"]    = false,
            ["scaling_level"]      = -2,
            ["scaling_off_x"]      = 0.0,
            ["scaling_off_y"]      = 0.0,
            ["virtual-camera"]     = new JsonObject { ["type2"] = 3 },
            ["modules"] = new JsonObject
            {
                ["auto-scene-switcher"] = new JsonObject
                {
                    ["interval"] = 300, ["non_matching_scene"] = "",
                    ["switch_if_not_matching"] = false, ["active"] = false, ["switches"] = new JsonArray()
                },
                ["output-timer"] = new JsonObject
                {
                    ["streamTimerHours"] = 0, ["streamTimerMinutes"] = 0, ["streamTimerSeconds"] = 30,
                    ["recordTimerHours"] = 0, ["recordTimerMinutes"] = 0, ["recordTimerSeconds"] = 30,
                    ["autoStartStreamTimer"] = false, ["autoStartRecordTimer"] = false, ["pauseRecordTimer"] = true
                },
                ["scripts-tool"] = new JsonArray()
            },
            ["version"] = 1,
            ["sources"] = sources
        };
    }

    // ── Helpers ──────────────────────────────────────────────────────────────

    private static string NewUuid() => Guid.NewGuid().ToString();

    private static JsonObject MakeSourceBase(
        string name, string srcId, string versionedId,
        JsonObject settings, JsonObject? extra = null)
    {
        var src = new JsonObject
        {
            ["prev_ver"]              = 536870916,
            ["name"]                  = name,
            ["uuid"]                  = NewUuid(),
            ["id"]                    = srcId,
            ["versioned_id"]          = versionedId,
            ["settings"]              = settings,
            ["mixers"]                = 255,
            ["sync"]                  = 0,
            ["flags"]                 = 0,
            ["volume"]                = 1.0,
            ["balance"]               = 0.5,
            ["enabled"]               = true,
            ["muted"]                 = false,
            ["push-to-mute"]          = false,
            ["push-to-mute-delay"]    = 0,
            ["push-to-talk"]          = false,
            ["push-to-talk-delay"]    = 0,
            ["hotkeys"]               = new JsonObject(),
            ["deinterlace_mode"]      = 0,
            ["deinterlace_field_order"] = 0,
            ["monitoring_type"]       = 0,
            ["private_settings"]      = new JsonObject()
        };

        if (extra != null)
            foreach (var kvp in extra)
                src[kvp.Key] = kvp.Value?.DeepClone();

        return src;
    }

    private static JsonObject MakeSceneItem(string name, string sourceUuid, int itemId, bool visible = true)
    {
        return new JsonObject
        {
            ["name"]              = name,
            ["source_uuid"]       = sourceUuid,
            ["visible"]           = visible,
            ["locked"]            = false,
            ["rot"]               = 0.0,
            ["align"]             = 5,
            ["bounds_type"]       = 0,
            ["bounds_align"]      = 0,
            ["bounds_crop"]       = false,
            ["crop_left"]         = 0,
            ["crop_top"]          = 0,
            ["crop_right"]        = 0,
            ["crop_bottom"]       = 0,
            ["id"]                = itemId,
            ["group_item_backup"] = false,
            ["pos"]               = new JsonObject { ["x"] = 0.0, ["y"] = 0.0 },
            ["scale"]             = new JsonObject { ["x"] = 1.0, ["y"] = 1.0 },
            ["bounds"]            = new JsonObject { ["x"] = 0.0, ["y"] = 0.0 },
            ["scale_filter"]      = "disable",
            ["blend_method"]      = "default",
            ["blend_type"]        = "normal",
            ["show_transition"]   = new JsonObject { ["duration"] = 0 },
            ["hide_transition"]   = new JsonObject { ["duration"] = 0 },
            ["private_settings"]  = new JsonObject()
        };
    }

    private static JsonObject MakeSceneSource(string sceneName, JsonArray items, int idCounter)
    {
        return MakeSourceBase(
            sceneName, "scene", "scene",
            new JsonObject
            {
                ["custom_size"] = false,
                ["id_counter"]  = idCounter,
                ["items"]       = items
            },
            new JsonObject
            {
                ["mixers"]      = 0,
                ["hotkeys"]     = new JsonObject { ["OBSBasic.SelectScene"] = new JsonArray() },
                ["canvas_uuid"] = DefaultCanvasUuid
            });
    }
}
