#include "m2_security.h"

bool check_permission_bits(uint32_t perm_bits, uint32_t owner_uid, uint32_t requesting_uid, char mode) {
    uint32_t bit_mask = 0;
    if (mode == 'r') bit_mask = 04;
    else if (mode == 'w') bit_mask = 02;
    else if (mode == 'x') bit_mask = 01;
    else return false;

    if (requesting_uid == owner_uid) {
        uint32_t owner_bits = (perm_bits >> 6) & 07;
        return (owner_bits & bit_mask) != 0;
    } else {
        uint32_t other_bits = perm_bits & 07;
        return (other_bits & bit_mask) != 0;
    }
}
