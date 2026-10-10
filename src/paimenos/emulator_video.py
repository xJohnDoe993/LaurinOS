"""Display defaults per parent-chosen hardware profile.

'low' is the conservative Broadwell-class baseline (console resolution, cheap GPU
presentation). Other profiles only change resolution and a few costly options.
See docs/emulator-performance.md and docs/hardware-profiles.md.
"""
from paimenos.emulator_catalog import CATALOG
from paimenos import hardware_profile


def video_settings(system, profile=None):
    if system not in CATALOG:
        raise ValueError('Unknown emulator system')
    profile = profile or hardware_profile.current()
    pixel_art = system not in ('ps1', 'n64', 'psp', 'dolphin')
    values = {
        'video_driver': 'gl',
        'video_windowed_fullscreen': 'true',
        'video_force_aspect': 'true',
        # ASPECT_RATIO_CORE in RetroArch 1.14 / 1.20; handhelds keep their ratio.
        'aspect_ratio_index': '22',
        'video_scale_integer': 'true' if pixel_art else 'false',
        'video_smooth': 'false' if pixel_art else 'true',
        'video_shader_enable': 'false',
        'video_filter': '',
        'video_vsync': 'true',
        'video_swap_interval': '1',
        'video_threaded': 'false',
        'video_hard_sync': 'false',
        'video_frame_delay': '0',
        'video_frame_delay_auto': 'false',
        'video_black_frame_insertion': '0',
        'vrr_runloop_enable': 'false',
        'audio_sync': 'true',
        'audio_latency': '64',
        'rewind_enable': 'false',
        'run_ahead_enabled': 'false',
        'preemptive_frames_enable': 'false',
    }
    if profile == 'ultra-low' and system != 'dolphin':
        # A video thread hides slow GPU drivers on old CPUs; costs about one frame of latency.
        # Not for Dolphin: its own CPU/GPU threads already run in parallel and timing/audio suffer.
        values.update(video_threaded='true', audio_latency='96')
    return values


def core_settings(system, profile=None):
    step = hardware_profile.level(profile)  # 0 ultra-low, 1 low, 2 medium, 3 high
    if system == 'ps1':
        resolution = ('1x(native)', '1x(native)', '2x', '4x')[step]
        return {
            'beetle_psx_internal_resolution': resolution,
            'beetle_psx_skip_bios': 'disabled',
            'beetle_psx_pgxp_mode': 'memory only' if step == 3 else 'disabled',
            'beetle_psx_cd_fastload': '2x(native)',
            'mednafen_psx_internal_resolution': resolution,
            'mednafen_psx_skip_bios': 'disabled',
        }
    if system == 'n64':
        values = {
            '-rdp-plugin': 'gliden64', '-rsp-plugin': 'hle',
            '-cpucore': 'dynamic_recompiler', '-aspect': '4:3',
            '-43screensize': ('320x240', '320x240', '640x480', '960x720')[step], '-169screensize': '640x360',
            '-EnableNativeResFactor': ('1', '1', '2', '3')[step], '-MultiSampling': '0',
            # Framebuffer emulation costs most on weak GPUs; a few effects may then be missing.
            '-EnableFBEmulation': 'False' if step == 0 else 'True', '-txEnhancementMode': 'None',
            '-txHiresEnable': 'False',
        }
        return {prefix + key: value for prefix in ('mupen64plus', 'mupen64plus-next')
                for key, value in values.items()}
    if system == 'dolphin':
        import platform
        return {
            # Current Dolphin libretro options use numeric enum values.
            'dolphin_cpu_core': '4' if platform.machine().lower() in ('aarch64', 'arm64') else '1',
            'dolphin_main_cpu_thread': 'enabled',
            'dolphin_renderer': 'Hardware',
            'dolphin_dsp_hle': 'enabled',
            # Native resolution in every profile: 2x dropped Twilight Princess below 30 FPS
            # with crackling audio even on 'high' devices.
            'dolphin_efb_scale': '1',
            'dolphin_aspect_ratio': '0',
            'dolphin_anti_aliasing': '0',
            'dolphin_max_anisotropy': '0',
            'dolphin_shader_compilation_mode': '0',
            'dolphin_widescreen_hack': 'disabled',
            'dolphin_load_custom_textures': 'disabled',
        }
    if system == 'psp':
        return {
            'ppsspp_cpu_core': 'JIT',
            'ppsspp_internal_resolution': ('480x272', '480x272', '960x544', '1440x816')[step],
            'ppsspp_backend': 'opengl',
            # Legacy core builds used a different backend key.
            'ppsspp_rendering_mode': 'OpenGL',
            'ppsspp_software_rendering': 'disabled',
            'ppsspp_texture_scaling_level': 'disabled',
            'ppsspp_texture_anisotropic_filtering': ('off', '2x', '4x', '8x')[step],
            'ppsspp_texture_deposterize': 'disabled',
            'ppsspp_texture_shader': 'disabled',
            'ppsspp_texture_replacement': 'disabled',
            'ppsspp_frameskip': 'disabled',
            'ppsspp_auto_frameskip': 'enabled' if step == 0 else 'disabled',
        }
    if system not in CATALOG:
        raise ValueError('Unknown emulator system')
    return {}


def config_lines(values):
    from paimenos.controller_profiles import quote
    return ''.join(key + ' = ' + quote(value) + '\n' for key, value in values.items())
