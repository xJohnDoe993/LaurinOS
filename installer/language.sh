#!/bin/bash
# Shared by the manual installer and the first-boot ISO setup.
# No package installation or Python dependency before the parent PIN prompt.
PAIMENOS_LANGUAGE=${PAIMENOS_LANGUAGE:-}
if [[ "${PAIMENOS_LANGUAGE,,}" != de && "${PAIMENOS_LANGUAGE,,}" != en ]]; then
    locale_value=''
    for locale_file in /etc/default/locale /etc/locale.conf; do
        [[ -r "$locale_file" ]] || continue
        declare -A locale_values=()
        while IFS= read -r locale_line || [[ -n "$locale_line" ]]; do
            if [[ "$locale_line" =~ ^[[:space:]]*(export[[:space:]]+)?(LC_ALL|LC_MESSAGES|LANG)[[:space:]]*=[[:space:]]*(.*)$ ]]; then
                locale_key=${BASH_REMATCH[2]}
                locale_value=${BASH_REMATCH[3]%% \#*}
                locale_value=${locale_value#"${locale_value%%[![:space:]]*}"}
                locale_value=${locale_value%"${locale_value##*[![:space:]]}"}
                locale_value=${locale_value#\"}; locale_value=${locale_value%\"}
                locale_value=${locale_value#\'}; locale_value=${locale_value%\'}
                [[ -z "$locale_value" ]] || locale_values[$locale_key]=$locale_value
            fi
        done < "$locale_file"
        locale_value=${locale_values[LC_ALL]:-${locale_values[LC_MESSAGES]:-${locale_values[LANG]:-}}}
        [[ -z "$locale_value" ]] || break
    done
    locale_value=${locale_value:-${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}}
    case "${locale_value,,}" in
        en|en_*|en.*|en-*|en@*) PAIMENOS_LANGUAGE=en ;;
        *) PAIMENOS_LANGUAGE=de ;;
    esac
else
    PAIMENOS_LANGUAGE=${PAIMENOS_LANGUAGE,,}
fi
export PAIMENOS_LANGUAGE
source "${REPO_DIR}/installer/english.sh"
paimenos_text() {
    local message=$1 index=0 value placeholder
    shift
    if [[ "$PAIMENOS_LANGUAGE" == en ]]; then
        message=${PAIMENOS_ENGLISH[$message]:-$message}
    fi
    for value in "$@"; do
        placeholder="{value${index}}"
        message=${message//"$placeholder"/"$value"}
        index=$((index + 1))
    done
    printf '%s' "$message"
}
unset locale_value locale_file locale_line locale_key locale_values
